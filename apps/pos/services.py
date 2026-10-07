from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.authorization import CAPABILITY_USE_POS, has_capability
from apps.accounts.models import User
from apps.bookings.models import Appointment, AppointmentStatusHistory
from apps.services.models import Service

from .models import CashierShift, Payment, PromoVoucher, ReceiptSequence, Sale, SaleItem


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
SALEABLE_APPOINTMENT_STATUSES = (
    Appointment.Status.PENDING,
    Appointment.Status.APPROVED,
    Appointment.Status.RESCHEDULED,
    Appointment.Status.ONGOING,
    Appointment.Status.COMPLETED,
)


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def calculate_totals(
    items,
    discount_type,
    discount_value,
    voucher=None,
    discount_id_number="",
    max_cap=None,
):
    subtotal = money(sum((item["line_total"] for item in items), ZERO))
    discount_value = money(discount_value or ZERO)
    if discount_value < ZERO:
        raise ValidationError("Discounts cannot be negative.")

    if discount_type == Sale.DiscountType.NONE:
        if discount_value != ZERO:
            raise ValidationError("Choose a discount type before entering a discount.")
        discount_amount = ZERO
    elif discount_type == Sale.DiscountType.FIXED:
        discount_amount = discount_value
    elif discount_type == Sale.DiscountType.PERCENT:
        if discount_value > Decimal("100.00"):
            raise ValidationError("Percentage discounts cannot exceed 100%.")
        discount_amount = money(subtotal * discount_value / Decimal("100.00"))
    elif discount_type == Sale.DiscountType.SENIOR_CITIZEN:
        if not str(discount_id_number).strip():
            raise ValidationError("Senior Citizen ID number is required.")
        # RA 9994 20% discount on services
        discount_amount = money(subtotal * Decimal("20.00") / Decimal("100.00"))
        if max_cap is not None and max_cap > ZERO:
            discount_amount = min(discount_amount, max_cap)
    elif discount_type == Sale.DiscountType.PWD:
        if not str(discount_id_number).strip():
            raise ValidationError("PWD ID number is required.")
        # RA 10754 20% discount on services
        discount_amount = money(subtotal * Decimal("20.00") / Decimal("100.00"))
        if max_cap is not None and max_cap > ZERO:
            discount_amount = min(discount_amount, max_cap)
    elif discount_type == Sale.DiscountType.PROMO_VOUCHER:
        if voucher is None:
            raise ValidationError("A valid promo voucher is required.")
        is_valid, reason = voucher.is_valid_for(subtotal)
        if not is_valid:
            raise ValidationError(reason)
        discount_amount = money(voucher.calculate_discount(subtotal))
    else:
        raise ValidationError("Choose a valid discount type.")

    if discount_amount > subtotal:
        raise ValidationError("The discount cannot exceed the subtotal.")
    total = money(subtotal - discount_amount)
    if total < ZERO:
        raise ValidationError("Sale totals cannot be negative.")
    return subtotal, discount_amount, total


def _next_receipt_number():
    sequence = ReceiptSequence.objects.select_for_update().get(pk=1)
    while True:
        sequence.last_value += 1
        receipt = f"GN-{timezone.localdate():%Y%m%d}-{sequence.last_value:08d}"
        if not Sale.objects.filter(receipt_number=receipt).exists():
            sequence.save(update_fields=("last_value", "updated_at"))
            return receipt


def _locked_items(raw_items):
    if not raw_items:
        raise ValidationError("Add at least one service to the sale.")

    service_items = [item for item in raw_items if item.get("service")]
    if not service_items:
        raise ValidationError("Add at least one service to the sale.")

    service_ids = [item["service"].pk for item in service_items]
    services = {
        service.pk: service
        for service in Service.objects.select_for_update().filter(
            pk__in=service_ids, is_active=True
        )
    }
    if len(services) != len(set(service_ids)):
        raise ValidationError("One or more selected services are unavailable.")

    staff_ids = {
        item["assigned_staff"].pk
        for item in service_items
        if item.get("assigned_staff") is not None
    }
    staff_members = {
        staff.pk: staff
        for staff in User.objects.select_for_update().filter(
            pk__in=staff_ids,
            role=User.Role.STAFF,
            is_active=True,
            is_active_staff_member=True,
        )
    }
    if len(staff_members) != len(staff_ids):
        raise ValidationError("One or more assigned staff members are unavailable.")

    items = []
    for position, raw_item in enumerate(raw_items):
        if not raw_item.get("service"):
            continue
        quantity = int(raw_item.get("quantity") or 1)
        if quantity < 1 or quantity > 100:
            raise ValidationError("Quantities must be between 1 and 100.")
        service = services[raw_item["service"].pk]
        staff = raw_item.get("assigned_staff")
        staff = staff_members[staff.pk] if staff else None
        unit_price = money(service.price)
        items.append(
            {
                "service": service,
                "staff": staff,
                "name": service.name,
                "category": service.category.name,
                "quantity": quantity,
                "unit_price": unit_price,
                "line_total": money(unit_price * quantity),
                "position": position,
            }
        )
    if not items:
        raise ValidationError("Add at least one service to the sale.")
    return items


def _validate_payment(payment_method, amount_tendered, total):
    amount_tendered = money(amount_tendered if amount_tendered is not None else total)
    if payment_method == Payment.Method.CASH:
        if amount_tendered < total:
            raise ValidationError("Cash tendered is insufficient for this sale.")
        return amount_tendered, money(amount_tendered - total)
    if payment_method not in Payment.Method.values:
        raise ValidationError("Choose a valid payment method.")
    if amount_tendered != total:
        raise ValidationError("Non-cash payments must match the sale total exactly.")
    return amount_tendered, ZERO


def create_sale(
    *,
    cashier,
    raw_items,
    payment_method,
    amount_tendered=None,
    payment_reference="",
    customer=None,
    appointment=None,
    discount_type=Sale.DiscountType.NONE,
    discount_value=ZERO,
    discount_id_number="",
    discount_id_name="",
    voucher=None,
    voucher_code=None,
    max_cap=None,
    shift=None,
    mark_appointment_completed=True,
):
    if not has_capability(cashier, CAPABILITY_USE_POS):
        raise PermissionDenied("You cannot process sales.")
    with transaction.atomic():
        if voucher_code and not voucher:
            from apps.pos.models import PromoVoucher
            voucher = PromoVoucher.objects.filter(code__iexact=voucher_code.strip()).first()
            if not voucher:
                raise ValidationError("Invalid promo voucher code.")
        items = _locked_items(raw_items)
        subtotal, discount_amount, total = calculate_totals(
            items,
            discount_type,
            discount_value,
            voucher=voucher,
            discount_id_number=discount_id_number,
            max_cap=max_cap,
        )
        amount_tendered, change = _validate_payment(
            payment_method, amount_tendered, total
        )

        locked_appointment = None
        if appointment is not None:
            locked_appointment = (
                Appointment.objects.select_for_update()
                .select_related("customer")
                .filter(pk=appointment.pk)
                .first()
            )
            if locked_appointment is None:
                raise ValidationError("The selected appointment is unavailable.")
            if locked_appointment.status not in SALEABLE_APPOINTMENT_STATUSES:
                raise ValidationError("The selected appointment cannot be checked out.")
            if Sale.objects.filter(appointment=locked_appointment).exists():
                raise ValidationError("The selected appointment already has a sale.")
            customer = locked_appointment.customer

        if shift is None:
            shift = CashierShift.objects.filter(
                cashier=cashier, status=CashierShift.Status.OPEN
            ).first()

        receipt_number = _next_receipt_number()
        sale = Sale.objects.create(
            receipt_number=receipt_number,
            shift=shift,
            customer=customer,
            customer_name_snapshot=customer.full_name if customer else "Walk-in customer",
            appointment=locked_appointment,
            subtotal=subtotal,
            discount_type=discount_type,
            discount_value=money(discount_value or ZERO),
            discount_amount=discount_amount,
            discount_id_number=discount_id_number.strip(),
            discount_id_name=discount_id_name.strip(),
            voucher=voucher,
            total=total,
            cashier=cashier,
            cashier_name_snapshot=str(cashier),
        )
        if voucher is not None:
            voucher.times_used += 1
            voucher.save(update_fields=("times_used", "updated_at"))

        SaleItem.objects.bulk_create(
            [
                SaleItem(
                    sale=sale,
                    service=item["service"],
                    assigned_staff=item["staff"],
                    service_name=item["name"],
                    service_category=item["category"],
                    staff_name=str(item["staff"]) if item["staff"] else "",
                    unit_price=item["unit_price"],
                    quantity=item["quantity"],
                    line_total=item["line_total"],
                    position=item["position"],
                )
                for item in items
            ]
        )
        Payment.objects.create(
            sale=sale,
            payment_method=payment_method,
            amount_tendered=amount_tendered,
            change=change,
            reference=payment_reference.strip(),
            recorded_by=cashier,
        )

        if (
            locked_appointment is not None
            and mark_appointment_completed
            and locked_appointment.status != Appointment.Status.COMPLETED
        ):
            previous = locked_appointment.status
            locked_appointment.status = Appointment.Status.COMPLETED
            locked_appointment.save(update_fields=("status", "updated_at"))
            AppointmentStatusHistory.objects.create(
                appointment=locked_appointment,
                from_status=previous,
                to_status=Appointment.Status.COMPLETED,
                actor=cashier,
                note=f"Completed through sale {receipt_number}",
            )
            from apps.monitoring.services import sync_services_for_appointment

            sync_services_for_appointment(
                locked_appointment,
                Appointment.Status.COMPLETED,
                actor=cashier,
                note=f"Completed through sale {receipt_number}",
            )
    return sale


def void_sale(sale, *, actor, reason):
    if not actor.is_owner:
        raise PermissionDenied("Only an owner can void sales.")
    reason = " ".join(reason.split())
    if not reason:
        raise ValidationError("A void reason is required.")
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk)
        if sale.status == Sale.Status.VOIDED:
            raise ValidationError("This sale is already voided.")
        sale.status = Sale.Status.VOIDED
        sale.void_reason = reason
        sale.voided_by = actor
        sale.voided_at = timezone.now()
        sale.save(
            update_fields=("status", "void_reason", "voided_by", "voided_at", "updated_at")
        )
    return sale
