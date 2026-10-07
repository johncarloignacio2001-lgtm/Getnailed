from datetime import timedelta
from decimal import Decimal

from allauth.account.decorators import reauthentication_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.authorization import CAPABILITY_USE_POS, is_owner
from apps.accounts.decorators import capability_required, owner_required
from apps.accounts.models import User
from apps.bookings.models import Appointment
from apps.services.models import Service

from .forms import (
    CheckoutForm,
    CheckoutItemFormSet,
    CloseShiftForm,
    OpenShiftForm,
    PromoVoucherForm,
    SaleHistoryFilterForm,
    VoidSaleForm,
)
from .models import CashierShift, Payment, PromoVoucher, Sale
from .services import create_sale, void_sale


def _appointment_initial(form, appointment_id):
    if not appointment_id:
        return {}, []
    appointment = form.fields["appointment"].queryset.filter(pk=appointment_id).first()
    if appointment is None:
        return {}, []
    items = []
    elapsed_minutes = 0
    for row in appointment.appointment_services.select_related("service").order_by("position", "pk"):
        if row.service_id and row.service and row.service.is_active:
            row_start = (appointment.scheduled_for + timedelta(minutes=elapsed_minutes)).time()
            items.append(
                {
                    "service": row.service_id,
                    "assigned_staff": row.assigned_staff_id or appointment.assigned_staff_id,
                    "service_time": row_start.strftime("%H:%M"),
                    "quantity": 1,
                }
            )
            elapsed_minutes += row.duration_minutes
    return {"appointment": appointment, "customer": appointment.customer}, items


@capability_required(CAPABILITY_USE_POS)
@require_http_methods(["GET"])
def api_appointment_details(request, pk):
    appointment = (
        Appointment.objects.exclude(
            status__in=(
                Appointment.Status.UNVERIFIED,
                Appointment.Status.REJECTED,
                Appointment.Status.CANCELLED,
                Appointment.Status.EXPIRED,
            )
        )
        .filter(sale__isnull=True, pk=pk)
        .select_related("customer", "assigned_staff")
        .first()
    )
    if not appointment:
        return JsonResponse(
            {"error": "Appointment not found or not eligible for checkout."},
            status=404,
        )
    items = []
    elapsed_minutes = 0
    for row in appointment.appointment_services.select_related("service").order_by("position", "pk"):
        if row.service_id and row.service and row.service.is_active:
            row_start = (appointment.scheduled_for + timedelta(minutes=elapsed_minutes)).time()
            items.append(
                {
                    "service_id": str(row.service_id),
                    "assigned_staff_id": str(row.assigned_staff_id or appointment.assigned_staff_id or ""),
                    "service_time": row_start.strftime("%H:%M"),
                }
            )
            elapsed_minutes += row.duration_minutes
    return JsonResponse(
        {
            "appointment_id": appointment.pk,
            "customer_id": str(appointment.customer_id) if appointment.customer_id else "",
            "customer_name": appointment.customer_name_snapshot,
            "appointment_date": appointment.appointment_date.isoformat(),
            "start_time": appointment.start_time.strftime("%H:%M"),
            "items": items,
        }
    )


@capability_required(CAPABILITY_USE_POS)
@require_http_methods(["GET", "POST"])
def index(request):
    form = CheckoutForm(request.POST if request.method == "POST" else None)
    initial_items = []
    if request.method == "GET":
        initial, initial_items = _appointment_initial(form, request.GET.get("appointment"))
        if initial:
            form = CheckoutForm(initial=initial)
    item_formset = CheckoutItemFormSet(
        request.POST if request.method == "POST" else None,
        prefix="items",
        initial=initial_items,
    )
    active_shift = CashierShift.objects.filter(
        cashier=request.user, status=CashierShift.Status.OPEN
    ).first()

    if request.method == "POST" and form.is_valid() and item_formset.is_valid():
        raw_items = [
            item_form.cleaned_data
            for item_form in item_formset.forms
            if item_form.cleaned_data
            and item_form.cleaned_data.get("service")
        ]
        try:
            sale = create_sale(
                cashier=request.user,
                raw_items=raw_items,
                customer=form.cleaned_data["customer"],
                appointment=form.cleaned_data["appointment"],
                discount_type=form.cleaned_data["discount_type"],
                discount_value=form.cleaned_data["discount_value"],
                discount_id_number=form.cleaned_data.get("discount_id_number", ""),
                discount_id_name=form.cleaned_data.get("discount_id_name", ""),
                voucher=form.cleaned_data.get("voucher_obj"),
                max_cap=form.cleaned_data.get("max_discount_cap"),
                payment_method=form.cleaned_data["payment_method"],
                amount_tendered=(
                    None
                    if form.cleaned_data["payment_method"] in (Payment.Method.GCASH, Payment.Method.MAYA)
                    else form.cleaned_data["amount_tendered"]
                ),
                payment_reference=form.cleaned_data["payment_reference"],
                shift=active_shift,
                mark_appointment_completed=form.cleaned_data[
                    "mark_appointment_completed"
                ],
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Sale {sale.receipt_number} completed.")
            return redirect("pos:receipt", receipt_number=sale.receipt_number)
    return render(
        request,
        "pos/index.html",
        {
            "form": form,
            "item_formset": item_formset,
            "active_shift": active_shift,
            "service_prices": {
                str(pk): str(price)
                for pk, price in Service.objects.filter(is_active=True).values_list(
                    "pk", "price"
                )
            },
        },
    )



@capability_required(CAPABILITY_USE_POS)
def history(request):
    sales = Sale.objects.visible_to(request.user).select_related(
        "customer", "cashier", "payment"
    )
    filter_form = SaleHistoryFilterForm(request.GET or None)
    if filter_form.is_valid():
        query = filter_form.cleaned_data["q"]
        if query:
            sales = sales.filter(
                Q(receipt_number__icontains=query)
                | Q(customer_name_snapshot__icontains=query)
            )
        if filter_form.cleaned_data["date"]:
            sales = sales.filter(created_at__date=filter_form.cleaned_data["date"])
        if filter_form.cleaned_data["status"]:
            sales = sales.filter(status=filter_form.cleaned_data["status"])
    page = Paginator(sales, 30).get_page(request.GET.get("page"))
    return render(request, "pos/history.html", {"page": page, "filter_form": filter_form})


@capability_required(CAPABILITY_USE_POS)
def receipt(request, receipt_number):
    sale = get_object_or_404(
        Sale.objects.visible_to(request.user)
        .select_related("customer", "appointment", "cashier", "payment")
        .prefetch_related("items"),
        receipt_number=receipt_number,
    )
    return render(request, "pos/receipt.html", {"sale": sale})


@owner_required
def void_approval(request):
    sales = Sale.objects.filter(status=Sale.Status.COMPLETED).select_related(
        "cashier", "payment"
    )[:100]
    return render(request, "pos/void_list.html", {"sales": sales})


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def void_detail(request, receipt_number):
    sale = get_object_or_404(
        Sale.objects.select_related("cashier", "payment").prefetch_related("items"),
        receipt_number=receipt_number,
    )
    form = VoidSaleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            void_sale(sale, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Sale {sale.receipt_number} was voided.")
            return redirect("pos:void_approval")
    return render(request, "pos/void_detail.html", {"sale": sale, "form": form})


@capability_required(CAPABILITY_USE_POS)
def shift_dashboard(request):
    active_shift = CashierShift.objects.filter(
        cashier=request.user, status=CashierShift.Status.OPEN
    ).first()

    current_stats = None
    if active_shift:
        sales = active_shift.sales.filter(status=Sale.Status.COMPLETED)
        from apps.pos.models import Payment
        payments = Payment.objects.filter(sale__in=sales)
        cash_sales = (
            payments.filter(payment_method=Payment.Method.CASH).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        ewallet_sales = (
            payments.filter(
                payment_method__in=[Payment.Method.GCASH, Payment.Method.MAYA]
            ).aggregate(s=models.Sum("sale__total"))["s"]
            or Decimal("0.00")
        )
        card_sales = (
            payments.filter(payment_method=Payment.Method.CARD).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        bank_sales = (
            payments.filter(payment_method=Payment.Method.BANK).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        total_sales = sales.aggregate(s=models.Sum("total"))["s"] or Decimal("0.00")
        expected_cash = active_shift.opening_cash + cash_sales
        current_stats = {
            "sales_count": sales.count(),
            "cash_sales": cash_sales,
            "ewallet_sales": ewallet_sales,
            "card_sales": card_sales,
            "bank_sales": bank_sales,
            "total_sales": total_sales,
            "expected_cash": expected_cash,
        }

    recent_shifts = (
        CashierShift.objects.all()
        if is_owner(request.user)
        else CashierShift.objects.filter(cashier=request.user)
    )[:10]

    return render(
        request,
        "pos/shift_dashboard.html",
        {
            "active_shift": active_shift,
            "current_stats": current_stats,
            "recent_shifts": recent_shifts,
        },
    )


@capability_required(CAPABILITY_USE_POS)
@require_http_methods(["GET", "POST"])
def shift_open(request):
    active = CashierShift.objects.filter(
        cashier=request.user, status=CashierShift.Status.OPEN
    ).first()
    if active:
        messages.info(request, f"You already have an active shift #{active.pk} open.")
        return redirect("pos:shift_dashboard")

    form = OpenShiftForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        shift = CashierShift.objects.create(
            cashier=request.user,
            opening_cash=form.cleaned_data["opening_cash"],
            notes=form.cleaned_data["notes"],
            status=CashierShift.Status.OPEN,
        )
        messages.success(
            request,
            f"Shift #{shift.pk} opened with starting drawer float of ₱{shift.opening_cash:,.2f}.",
        )
        return redirect("pos:shift_dashboard")
    return render(request, "pos/shift_open.html", {"form": form})


@capability_required(CAPABILITY_USE_POS)
@require_http_methods(["GET", "POST"])
def shift_close(request):
    active = CashierShift.objects.filter(
        cashier=request.user, status=CashierShift.Status.OPEN
    ).first()
    if not active:
        messages.warning(request, "You do not have an open shift to reconcile.")
        return redirect("pos:shift_dashboard")

    sales = active.sales.filter(status=Sale.Status.COMPLETED)
    from apps.pos.models import Payment
    payments = Payment.objects.filter(sale__in=sales)
    cash_sales = (
        payments.filter(payment_method=Payment.Method.CASH).aggregate(
            s=models.Sum("sale__total")
        )["s"]
        or Decimal("0.00")
    )
    ewallet_sales = (
        payments.filter(
            payment_method__in=[Payment.Method.GCASH, Payment.Method.MAYA]
        ).aggregate(s=models.Sum("sale__total"))["s"]
        or Decimal("0.00")
    )
    expected_cash = active.opening_cash + cash_sales

    form = CloseShiftForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        closing_cash = form.cleaned_data["closing_cash"]
        notes = form.cleaned_data["notes"]
        active.reconcile(closing_cash, request.user, notes=notes)
        messages.success(
            request,
            f"Shift #{active.pk} successfully closed. Variance: ₱{active.cash_variance:+,.2f}.",
        )
        return redirect("pos:shift_reconciliation", pk=active.pk)

    return render(
        request,
        "pos/shift_close.html",
        {
            "form": form,
            "shift": active,
            "cash_sales": cash_sales,
            "ewallet_sales": ewallet_sales,
            "expected_cash": expected_cash,
        },
    )


@capability_required(CAPABILITY_USE_POS)
def shift_reconciliation(request, pk):
    shift = get_object_or_404(CashierShift, pk=pk)
    if not is_owner(request.user) and shift.cashier != request.user:
        raise PermissionDenied("You do not have permission to view this till reconciliation.")
    return render(request, "pos/shift_reconciliation.html", {"shift": shift})


@capability_required(CAPABILITY_USE_POS)
def shift_history(request):
    shifts = (
        CashierShift.objects.all()
        if is_owner(request.user)
        else CashierShift.objects.filter(cashier=request.user)
    )
    date_filter = request.GET.get("date")
    if date_filter:
        shifts = shifts.filter(opened_at__date=date_filter)
    cashier_id = request.GET.get("cashier")
    if is_owner(request.user) and cashier_id and cashier_id.isdigit():
        shifts = shifts.filter(cashier_id=cashier_id)

    page = Paginator(shifts, 20).get_page(request.GET.get("page"))
    cashiers = User.objects.filter(role__in=[User.Role.CASHIER, User.Role.OWNER, User.Role.STAFF])
    return render(
        request,
        "pos/shift_history.html",
        {"page": page, "cashiers": cashiers, "date_filter": date_filter},
    )


@owner_required
def voucher_list(request):
    vouchers = PromoVoucher.objects.all()
    return render(request, "pos/voucher_list.html", {"vouchers": vouchers})


@owner_required
@require_http_methods(["GET", "POST"])
def voucher_create(request):
    form = PromoVoucherForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        voucher = form.save()
        messages.success(request, f"Promo voucher {voucher.code} created.")
        return redirect("pos:voucher_list")
    return render(request, "pos/voucher_form.html", {"form": form})

