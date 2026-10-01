import secrets
from datetime import datetime, timedelta
from urllib.parse import urljoin

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.accounts.emails import send_branded_email
from apps.accounts.models import User
from apps.customers.models import Customer
from apps.notifications.models import Notification
from apps.services.models import Service, StaffProfile

from .models import Appointment, AppointmentService, AppointmentStatusHistory, Booking


BLOCKING_STATUSES = (
    Appointment.Status.UNVERIFIED,
    Appointment.Status.PENDING,
    Appointment.Status.APPROVED,
    Appointment.Status.RESCHEDULED,
    Appointment.Status.ONGOING,
)
MANAGER_TRANSITIONS = {
    Appointment.Status.PENDING: {
        Appointment.Status.APPROVED,
        Appointment.Status.REJECTED,
        Appointment.Status.RESCHEDULED,
        Appointment.Status.CANCELLED,
    },
    Appointment.Status.APPROVED: {
        Appointment.Status.RESCHEDULED,
        Appointment.Status.ONGOING,
        Appointment.Status.COMPLETED,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.RESCHEDULED: {
        Appointment.Status.APPROVED,
        Appointment.Status.ONGOING,
        Appointment.Status.CANCELLED,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.ONGOING: {
        Appointment.Status.COMPLETED,
        Appointment.Status.CANCELLED,
    },
}
STAFF_TRANSITIONS = {
    Appointment.Status.APPROVED: {
        Appointment.Status.ONGOING,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.RESCHEDULED: {
        Appointment.Status.ONGOING,
        Appointment.Status.NO_SHOW,
    },
    Appointment.Status.ONGOING: {Appointment.Status.COMPLETED},
}


def _public_url(request, path):
    if settings.PUBLIC_BASE_URL:
        return urljoin(f"{settings.PUBLIC_BASE_URL.rstrip('/')}/", path.lstrip("/"))
    return request.build_absolute_uri(path)


def _new_verification_code():
    return f"{secrets.randbelow(100_000_000):08d}"


def _send_verification_email(booking, code, request):
    verify_url = _public_url(request, reverse("bookings:verify"))
    send_branded_email(
        booking.email,
        f"Verify booking {booking.reference}",
        "bookings/emails/verify",
        {"booking": booking, "code": code, "verify_url": verify_url},
    )


def _send_confirmed_email(booking, token, request):
    access_path = reverse(
        "bookings:public_status",
        kwargs={"reference": booking.reference, "token": token},
    )
    send_branded_email(
        booking.email,
        f"Booking received: {booking.reference}",
        "bookings/emails/confirmed",
        {"booking": booking, "access_url": _public_url(request, access_path)},
    )


def _send_status_email(appointment):
    if not appointment.email:
        return
    send_branded_email(
        appointment.email,
        f"Appointment update: {appointment.reference}",
        "bookings/emails/status_update",
        {"appointment": appointment},
    )


def _appointment_end(appointment_date, start_time, duration_minutes):
    start = datetime.combine(appointment_date, start_time)
    end = start + timedelta(minutes=duration_minutes)
    if end.date() != appointment_date:
        raise ValidationError("The selected services must finish on the appointment date.")
    return end.time()


def _lock_and_validate_staff(staff):
    if staff is None:
        return None
    staff = User.objects.select_for_update().filter(pk=staff.pk, role=User.Role.STAFF).first()
    if staff is None or not staff.is_active or not staff.is_active_staff_member:
        raise ValidationError("The selected staff member is not available.")
    profile = StaffProfile.objects.select_for_update().filter(user=staff).first()
    if (
        profile is None
        or not profile.is_active
        or profile.availability_status != StaffProfile.Availability.AVAILABLE
    ):
        raise ValidationError("The selected staff member is not accepting appointments.")
    return staff


def _validate_no_overlap(staff, appointment_date, start_time, end_time, exclude=None):
    if staff is None:
        return
    overlapping = Appointment.objects.filter(
        assigned_staff=staff,
        appointment_date=appointment_date,
        status__in=BLOCKING_STATUSES,
        start_time__lt=end_time,
        end_time__gt=start_time,
    )
    if exclude:
        overlapping = overlapping.exclude(pk=exclude)
    if overlapping.exists():
        raise ValidationError("That staff member already has an appointment during this time.")


def _notification_recipients(appointment, include_managers=False):
    query = Q(pk=appointment.assigned_staff_id) if appointment.assigned_staff_id else Q(pk__in=[])
    if include_managers:
        query |= Q(role__in=(User.Role.OWNER, User.Role.CASHIER))
    return User.objects.filter(query, is_active=True).distinct()


def _create_notifications(appointment, event_type, title, message, include_managers=False):
    Notification.objects.bulk_create(
        [
            Notification(
                recipient=recipient,
                appointment=appointment,
                event_type=event_type,
                title=title,
                message=message,
            )
            for recipient in _notification_recipients(appointment, include_managers)
        ]
    )


def create_public_appointment(cleaned_data, services, request):
    now = timezone.now()
    service_ids = list(dict.fromkeys(item.pk for item in services))
    with transaction.atomic():
        services = list(
            Service.objects.select_for_update().filter(pk__in=service_ids, is_active=True)
        )
        if not services or len(services) != len(service_ids):
            raise ValidationError("Choose only currently available services.")
        duration = sum(item.duration_minutes for item in services)
        end_time = _appointment_end(
            cleaned_data["appointment_date"], cleaned_data["start_time"], duration
        )
        staff = _lock_and_validate_staff(cleaned_data.get("assigned_staff"))
        _validate_no_overlap(
            staff,
            cleaned_data["appointment_date"],
            cleaned_data["start_time"],
            end_time,
        )
        email = cleaned_data["email"].strip().lower()
        customer = None
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_customer:
            customer = Customer.objects.select_for_update().filter(user=request.user).first()
            if customer is None:
                raise ValidationError("Your customer profile is not connected to this account.")
            if customer.email.lower() != email:
                raise ValidationError("Use the email address connected to your customer account.")
        else:
            customer, _ = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": cleaned_data["first_name"],
                    "last_name": cleaned_data["last_name"],
                    "phone": cleaned_data.get("phone", ""),
                },
            )
        changed = []
        for field in ("first_name", "last_name", "phone"):
            value = cleaned_data.get(field, "")
            if value and getattr(customer, field) != value:
                setattr(customer, field, value)
                changed.append(field)
        if changed:
            customer.save(update_fields=(*changed, "updated_at"))
        appointment = Appointment.objects.create(
            customer=customer,
            customer_name_snapshot=customer.full_name,
            customer_email_snapshot=email,
            customer_phone_snapshot=cleaned_data.get("phone", ""),
            appointment_date=cleaned_data["appointment_date"],
            start_time=cleaned_data["start_time"],
            end_time=end_time,
            assigned_staff=staff,
            notes=cleaned_data.get("notes", ""),
            expires_at=now + settings.BOOKING_UNVERIFIED_TIMEOUT,
        )
        AppointmentService.objects.bulk_create(
            [
                AppointmentService(
                    appointment=appointment,
                    service=service,
                    service_name=service.name,
                    duration_minutes=service.duration_minutes,
                    price=service.price,
                    assigned_staff=staff,
                    position=position,
                )
                for position, service in enumerate(services)
            ]
        )
        code = _new_verification_code()
        appointment.set_verification_code(
            code,
            min(appointment.expires_at, now + settings.BOOKING_VERIFICATION_CODE_TIMEOUT),
        )
        appointment.save(
            update_fields=(
                "verification_code_digest",
                "verification_code_expires_at",
                "verification_failed_attempts",
                "verification_sent_at",
                "updated_at",
            )
        )
        _send_verification_email(appointment, code, request)
    return appointment


def create_public_booking(cleaned_data, request):
    """Compatibility path for previously shipped free-text booking clients."""
    now = timezone.now()
    with transaction.atomic():
        booking = Booking(**cleaned_data, expires_at=now + settings.BOOKING_UNVERIFIED_TIMEOUT)
        code = _new_verification_code()
        booking.set_verification_code(
            code,
            min(booking.expires_at, now + settings.BOOKING_VERIFICATION_CODE_TIMEOUT),
        )
        booking.save()
        _send_verification_email(booking, code, request)
    return booking


def _find_unverified_for_update(reference, email=None):
    appointment_query = Appointment.objects.select_for_update().filter(
        booking_reference=reference.strip(), status=Appointment.Status.UNVERIFIED
    )
    if email is not None:
        appointment_query = appointment_query.filter(customer_email_snapshot=email)
    appointment = appointment_query.first()
    if appointment:
        return appointment
    booking_query = Booking.objects.select_for_update().filter(
        reference=reference.strip(), status=Booking.Status.UNVERIFIED
    )
    if email is not None:
        booking_query = booking_query.filter(email=email)
    return booking_query.first()


def resend_verification(reference, email, request):
    now = timezone.now()
    email = email.strip().lower()
    with transaction.atomic():
        booking = _find_unverified_for_update(reference, email)
        if booking is None:
            return False
        if booking.expires_at <= now:
            booking.expire_if_needed()
            return False
        if booking.verification_resend_count >= settings.BOOKING_MAX_RESENDS:
            return False
        if booking.verification_sent_at and booking.verification_sent_at + settings.BOOKING_RESEND_COOLDOWN > now:
            return False
        code = _new_verification_code()
        booking.set_verification_code(
            code,
            min(booking.expires_at, now + settings.BOOKING_VERIFICATION_CODE_TIMEOUT),
        )
        booking.verification_resend_count += 1
        booking.save(
            update_fields=(
                "verification_code_digest",
                "verification_code_expires_at",
                "verification_failed_attempts",
                "verification_sent_at",
                "verification_resend_count",
                "updated_at",
            )
        )
        _send_verification_email(booking, code, request)
    return True


def verify_public_booking(reference, code, request):
    now = timezone.now()
    with transaction.atomic():
        booking = _find_unverified_for_update(reference)
        if booking is None:
            return None, None
        if booking.expires_at <= now:
            booking.expire_if_needed()
            return None, None
        if (
            booking.verification_failed_attempts >= settings.BOOKING_VERIFICATION_MAX_ATTEMPTS
            or not booking.verification_code_expires_at
            or booking.verification_code_expires_at <= now
        ):
            return None, None
        if not booking.matches_verification_code(code.strip()):
            booking.verification_failed_attempts += 1
            booking.save(update_fields=("verification_failed_attempts", "updated_at"))
            return None, None

        token = booking.issue_public_access_token(now + settings.BOOKING_ACCESS_TOKEN_TIMEOUT)
        booking.status = (
            Appointment.Status.PENDING if isinstance(booking, Appointment) else Booking.Status.CONFIRMED
        )
        booking.verified_at = now
        booking.verification_code_digest = ""
        booking.save(
            update_fields=(
                "status",
                "verified_at",
                "verification_code_digest",
                "public_access_token_digest",
                "public_access_expires_at",
                "updated_at",
            )
        )
        if isinstance(booking, Appointment):
            AppointmentStatusHistory.objects.create(
                appointment=booking,
                from_status=Appointment.Status.UNVERIFIED,
                to_status=Appointment.Status.PENDING,
            )
            _create_notifications(
                booking,
                Notification.EventType.NEW,
                "New appointment request",
                f"{booking.customer_name} requested {booking.service_name}.",
                include_managers=True,
            )
        _send_confirmed_email(booking, token, request)
    return booking, token


def get_public_booking(reference, token):
    booking = Appointment.objects.filter(booking_reference=reference.strip()).first()
    if booking is None:
        booking = Booking.objects.filter(reference=reference.strip()).first()
    if booking is None or not booking.accepts_public_access_token(token):
        return None
    return booking


def cancel_public_booking(reference, token):
    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().filter(booking_reference=reference).first()
        if appointment:
            if (
                not appointment.accepts_public_access_token(token)
                or appointment.status
                not in (
                    Appointment.Status.PENDING,
                    Appointment.Status.APPROVED,
                    Appointment.Status.RESCHEDULED,
                )
            ):
                return None
            previous = appointment.status
            appointment.status = Appointment.Status.CANCELLED
            appointment.cancelled_at = timezone.now()
            appointment.save(update_fields=("status", "cancelled_at", "updated_at"))
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                from_status=previous,
                to_status=appointment.status,
                note="Cancelled by customer",
            )
            _create_notifications(
                appointment,
                Notification.EventType.CANCELLED,
                "Appointment cancelled",
                f"{appointment.customer_name} cancelled {appointment.reference}.",
                include_managers=True,
            )
            return appointment

        booking = Booking.objects.select_for_update().filter(reference=reference).first()
        if (
            booking is None
            or not booking.accepts_public_access_token(token)
            or booking.status != Booking.Status.CONFIRMED
        ):
            return None
        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=("status", "cancelled_at", "updated_at"))
        return booking


def reschedule_public_booking(reference, token, scheduled_for):
    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().filter(booking_reference=reference).first()
        if appointment:
            if (
                not appointment.accepts_public_access_token(token)
                or appointment.status
                not in (
                    Appointment.Status.PENDING,
                    Appointment.Status.APPROVED,
                    Appointment.Status.RESCHEDULED,
                )
            ):
                return None
            staff = _lock_and_validate_staff(appointment.assigned_staff)
            appointment_date = timezone.localtime(scheduled_for).date()
            start_time = timezone.localtime(scheduled_for).time().replace(tzinfo=None)
            end_time = _appointment_end(
                appointment_date, start_time, appointment.total_duration_minutes
            )
            _validate_no_overlap(
                staff, appointment_date, start_time, end_time, exclude=appointment.pk
            )
            previous = appointment.status
            appointment.appointment_date = appointment_date
            appointment.start_time = start_time
            appointment.end_time = end_time
            appointment.status = Appointment.Status.RESCHEDULED
            appointment.save(
                update_fields=(
                    "appointment_date",
                    "start_time",
                    "end_time",
                    "status",
                    "updated_at",
                )
            )
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                from_status=previous,
                to_status=appointment.status,
                note="Rescheduled by customer",
            )
            _create_notifications(
                appointment,
                Notification.EventType.RESCHEDULED,
                "Appointment rescheduled",
                f"{appointment.reference} requires approval for its new time.",
                include_managers=True,
            )
            return appointment

        booking = Booking.objects.select_for_update().filter(reference=reference).first()
        if (
            booking is None
            or not booking.accepts_public_access_token(token)
            or booking.status != Booking.Status.CONFIRMED
        ):
            return None
        booking.scheduled_for = scheduled_for
        booking.save(update_fields=("scheduled_for", "updated_at"))
        return booking


def transition_appointment(appointment, new_status, actor, note=""):
    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
        if actor.is_service_staff and not actor.is_owner:
            if appointment.assigned_staff_id != actor.pk:
                raise PermissionDenied("This appointment is not assigned to you.")
            transitions = STAFF_TRANSITIONS
        elif actor.is_owner or actor.is_cashier:
            transitions = MANAGER_TRANSITIONS
        else:
            raise PermissionDenied("You cannot update appointment statuses.")
        if new_status not in transitions.get(appointment.status, set()):
            raise ValidationError("That status transition is not allowed.")
        previous = appointment.status
        appointment.status = new_status
        if new_status == Appointment.Status.CANCELLED:
            appointment.cancelled_at = timezone.now()
            appointment.cancellation_reason = note
        appointment.save(
            update_fields=("status", "cancelled_at", "cancellation_reason", "updated_at")
        )
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            from_status=previous,
            to_status=new_status,
            actor=actor,
            note=note,
        )
        from apps.monitoring.services import sync_services_for_appointment

        sync_services_for_appointment(appointment, new_status, actor=actor, note=note)
        event_type = {
            Appointment.Status.APPROVED: Notification.EventType.APPROVED,
            Appointment.Status.REJECTED: Notification.EventType.REJECTED,
            Appointment.Status.RESCHEDULED: Notification.EventType.RESCHEDULED,
            Appointment.Status.CANCELLED: Notification.EventType.CANCELLED,
        }.get(new_status)
        if event_type:
            _create_notifications(
                appointment,
                event_type,
                f"Appointment {appointment.get_status_display().lower()}",
                f"{appointment.reference} is now {appointment.get_status_display().lower()}.",
            )
            _send_status_email(appointment)
    return appointment


def update_appointment_schedule(
    appointment, *, appointment_date, start_time, assigned_staff, actor
):
    if not (actor.is_owner or actor.is_cashier):
        raise PermissionDenied("You cannot assign or reschedule appointments.")
    with transaction.atomic():
        appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
        staff = _lock_and_validate_staff(assigned_staff)
        end_time = _appointment_end(
            appointment_date, start_time, appointment.total_duration_minutes
        )
        _validate_no_overlap(
            staff, appointment_date, start_time, end_time, exclude=appointment.pk
        )
        schedule_changed = (
            appointment.appointment_date != appointment_date
            or appointment.start_time != start_time
        )
        previous = appointment.status
        appointment.appointment_date = appointment_date
        appointment.start_time = start_time
        appointment.end_time = end_time
        appointment.assigned_staff = staff
        appointment.requires_schedule_review = False
        if schedule_changed and appointment.status in (
            Appointment.Status.PENDING,
            Appointment.Status.APPROVED,
            Appointment.Status.RESCHEDULED,
        ):
            appointment.status = Appointment.Status.RESCHEDULED
        appointment.save(
            update_fields=(
                "appointment_date",
                "start_time",
                "end_time",
                "assigned_staff",
                "requires_schedule_review",
                "status",
                "updated_at",
            )
        )
        appointment.appointment_services.update(assigned_staff=staff)
        if appointment.status != previous:
            AppointmentStatusHistory.objects.create(
                appointment=appointment,
                from_status=previous,
                to_status=appointment.status,
                actor=actor,
                note="Schedule updated by management",
            )
        _create_notifications(
            appointment,
            Notification.EventType.RESCHEDULED if schedule_changed else Notification.EventType.NEW,
            "Appointment assignment updated",
            f"You are assigned to {appointment.reference} on {appointment.appointment_date}.",
        )
        if schedule_changed:
            _send_status_email(appointment)
    return appointment
