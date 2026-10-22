from datetime import datetime

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from apps.accounts.authorization import CAPABILITY_MANAGE_BOOKINGS
from apps.accounts.decorators import (
    authenticated_internal_user_required,
    capability_required,
    staff_required,
)
from apps.audittrail.events import record_security_event
from apps.audittrail.models import SecurityEvent
from apps.bookings.security import (
    check_ip_booking_rate_limit,
    check_email_pending_limit,
    log_spam_blocked,
)
from apps.services.models import Service

from .forms import (
    AppointmentFilterForm,
    AppointmentScheduleForm,
    AppointmentStatusForm,
    BookingCancellationForm,
    BookingLookupForm,
    BookingRescheduleForm,
    BookingResendForm,
    BookingVerificationForm,
    PublicBookingForm,
    PublicContactForm,
    PublicScheduleForm,
    PublicServiceForm,
)
from .models import Appointment, Booking
from .services import (
    cancel_public_booking,
    create_internal_appointment,
    create_public_appointment,
    create_public_booking,
    get_available_time_slots,
    get_public_booking,
    resend_verification,
    reschedule_public_booking,
    transition_appointment,
    update_appointment_schedule,
    verify_public_booking,
)


GENERIC_VERIFICATION_ERROR = "The booking details or verification code are invalid or unavailable."
GENERIC_ACCESS_ERROR = "The booking access details are invalid or unavailable."
WIZARD_SESSION_KEY = "public_appointment_wizard"


def _wizard_data(request):
    return request.session.get(WIZARD_SESSION_KEY, {})


@never_cache
@require_http_methods(["GET", "POST"])
def index(request):
    # Accept the shipped single-request payload while browsers use the canonical wizard.
    if request.method == "POST" and (
        "service_name" in request.POST or not any(key in request.POST for key in ("first_name", "last_name"))
    ):
        legacy_form = PublicBookingForm(request.POST)
        if legacy_form.is_valid():
            booking = create_public_booking(legacy_form.cleaned_data, request)
            messages.success(request, "Check your email for a verification code.")
            return redirect(f"{reverse('bookings:verify')}?reference={booking.reference}")
        return render(request, "bookings/public_booking.html", {"form": legacy_form})

    initial = {}
    if request.user.is_authenticated and getattr(request.user, "is_customer", False):
        customer = getattr(request.user, "customer_profile", None)
        initial = {
            "first_name": customer.first_name if customer else request.user.first_name,
            "last_name": customer.last_name if customer else request.user.last_name,
            "email": customer.email if customer and customer.email else request.user.email,
            "phone_number": customer.phone if customer and customer.phone else getattr(request.user, "phone_number", ""),
        }
        service_id = request.GET.get("service")
        if service_id and service_id.isdigit() and initial.get("first_name") and initial.get("email"):
            service_obj = Service.objects.filter(pk=service_id, is_active=True).first()
            if service_obj:
                request.session[WIZARD_SESSION_KEY] = {
                    "contact": initial,
                    "service_ids": [service_obj.pk],
                }
                return redirect("bookings:select_schedule")

    is_internal = request.user.is_authenticated and (
        getattr(request.user, "is_owner", False)
        or getattr(request.user, "is_cashier", False)
        or getattr(request.user, "can_manage_bookings", False)
    )
    form = PublicContactForm(
        request.POST if request.method == "POST" else None,
        initial=initial,
        is_internal=is_internal,
    )
    if request.method == "POST" and form.is_valid():
        contact_data = {
            "first_name": form.cleaned_data.get("first_name", ""),
            "last_name": form.cleaned_data.get("last_name", ""),
            "email": form.cleaned_data.get("email", ""),
            "phone": form.cleaned_data.get("phone", ""),
            "notes": form.cleaned_data.get("notes", ""),
            "customer_id": (
                form.cleaned_data["customer"].pk
                if form.cleaned_data.get("customer")
                else None
            ),
        }
        request.session[WIZARD_SESSION_KEY] = {"contact": contact_data}
        return redirect("bookings:select_services")
    return render(
        request,
        "bookings/public_booking.html",
        {
            "form": form,
            "step": 1,
            "step_title": "Customer details" if is_internal else "Your details",
            "button_label": "Choose services",
            "is_internal": is_internal,
        },
    )


@never_cache
@require_http_methods(["GET", "POST"])
def select_services(request):
    data = _wizard_data(request)
    if "contact" not in data:
        return redirect("bookings:index")
    service_id = request.GET.get("service")
    initial_services = [int(service_id)] if service_id and service_id.isdigit() else data.get("service_ids", [])
    form = PublicServiceForm(
        request.POST if request.method == "POST" else None,
        initial={"services": initial_services} if initial_services and request.method == "GET" else None,
    )
    if request.method == "POST" and form.is_valid():
        data["service_ids"] = list(form.cleaned_data["services"].values_list("pk", flat=True))
        request.session[WIZARD_SESSION_KEY] = data
        return redirect("bookings:select_schedule")
    return render(
        request,
        "bookings/public_booking.html",
        {"form": form, "step": 2, "step_title": "Services", "button_label": "Choose a time"},
    )


@never_cache
@require_http_methods(["GET", "POST"])
def select_schedule(request):
    data = _wizard_data(request)
    if "contact" not in data or not data.get("service_ids"):
        return redirect("bookings:index")
    services = list(Service.objects.filter(pk__in=data.get("service_ids", []), is_active=True))
    form = PublicScheduleForm(
        request.POST if request.method == "POST" else None,
        services=services,
    )
    if request.method == "POST" and form.is_valid():
        data["schedule"] = {
            "appointment_date": form.cleaned_data["appointment_date"].isoformat(),
            "start_time": form.cleaned_data["start_time"].isoformat(),
            "assigned_staff_id": getattr(form.cleaned_data["assigned_staff"], "pk", None),
        }
        request.session[WIZARD_SESSION_KEY] = data
        return redirect("bookings:review")
    total_duration = sum(s.duration_minutes for s in services)
    return render(
        request,
        "bookings/public_booking.html",
        {
            "form": form,
            "step": 3,
            "step_title": "Schedule",
            "button_label": "Review request",
            "service_ids": data.get("service_ids", []),
            "services": services,
            "total_duration": total_duration,
        },
    )


@never_cache
@require_http_methods(["GET"])
def api_available_slots(request):
    date_str = request.GET.get("date")
    if not date_str:
        return JsonResponse({"slots": []})
    try:
        appointment_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse({"slots": [], "error": "Invalid date format."})

    service_ids = request.GET.getlist("services")
    if not service_ids and request.GET.get("service_ids"):
        service_ids = [s.strip() for s in request.GET.get("service_ids").split(",") if s.strip()]

    if not service_ids:
        data = _wizard_data(request)
        service_ids = data.get("service_ids", [])

    staff_id = request.GET.get("staff")
    if staff_id and staff_id.isdigit():
        staff_id = int(staff_id)
    else:
        staff_id = None

    slots = get_available_time_slots(appointment_date, service_ids, staff_id=staff_id)
    return JsonResponse({"slots": slots})



@never_cache
@require_http_methods(["GET", "POST"])
def review(request):
    data = _wizard_data(request)
    if "contact" not in data or not data.get("service_ids") or "schedule" not in data:
        return redirect("bookings:index")
    services = list(Service.objects.filter(pk__in=data["service_ids"], is_active=True))
    schedule_form = PublicScheduleForm(
        data={
            "appointment_date": data["schedule"]["appointment_date"],
            "start_time": data["schedule"]["start_time"],
            "assigned_staff": data["schedule"].get("assigned_staff_id") or "",
        },
        services=services,
    )
    if not services or not schedule_form.is_valid():
        request.session.pop(WIZARD_SESSION_KEY, None)
        messages.error(request, "Your selection is no longer available. Please start again.")
        return redirect("bookings:index")
    appointment_data = {**data["contact"], **schedule_form.cleaned_data}
    if data["contact"].get("customer_id"):
        from apps.customers.models import Customer
        customer_obj = Customer.objects.filter(pk=data["contact"]["customer_id"]).first()
        if customer_obj:
            appointment_data["customer"] = customer_obj

    assigned_staff_obj = schedule_form.cleaned_data.get("assigned_staff")
    total_duration = sum(s.duration_minutes for s in services)
    total_price = sum(s.price for s in services)

    is_internal_admin = (
        request.user.is_authenticated
        and (
            getattr(request.user, "is_owner", False)
            or getattr(request.user, "is_cashier", False)
            or getattr(request.user, "can_manage_bookings", False)
        )
    )

    if request.method == "POST":
        if not is_internal_admin:
            is_ip_allowed, _ = check_ip_booking_rate_limit(request, max_attempts=12, window_seconds=600)
            if not is_ip_allowed:
                log_spam_blocked(request, "IP rate limit exceeded")
                messages.error(
                    request,
                    "Too many appointment requests detected from your network. Please wait a few minutes before trying again to prevent spam.",
                )
                return redirect("bookings:review")

            email = appointment_data.get("email", "").strip().lower()
            if not check_email_pending_limit(email, max_pending=5):
                log_spam_blocked(request, "Email pending spam limit exceeded", email=email)
                messages.error(
                    request,
                    "Multiple pending booking requests already exist for this email address. Please check your inbox or wait before creating another.",
                )
                return redirect("bookings:review")

        try:
            if is_internal_admin:
                appointment = create_internal_appointment(
                    appointment_data,
                    services,
                    actor=request.user,
                    request=request,
                    booking_source=Appointment.BookingSource.WALK_IN,
                    initial_status=Appointment.Status.APPROVED,
                )
            else:
                appointment = create_public_appointment(appointment_data, services, request)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        else:
            request.session.pop(WIZARD_SESSION_KEY, None)
            if is_internal_admin:
                staff_name = (
                    appointment.assigned_staff.get_full_name()
                    if appointment.assigned_staff
                    else "Technician"
                )
                messages.success(
                    request,
                    f"Appointment #{appointment.reference} confirmed and assigned to {staff_name} successfully!",
                )
                return redirect("bookings:detail", reference=appointment.reference)
            else:
                messages.success(
                    request,
                    "Check your email for a verification code. Your request is not visible to the salon until verified.",
                )
                return redirect(f"{reverse('bookings:verify')}?reference={appointment.reference}")
    return render(
        request,
        "bookings/review.html",
        {
            "contact": data["contact"],
            "schedule": schedule_form.cleaned_data,
            "services": services,
            "assigned_staff_obj": assigned_staff_obj,
            "total_duration": total_duration,
            "total_price": total_price,
            "is_internal_admin": is_internal_admin,
            "step": 4,
            "step_title": "Review Appointment & Technician",
            "button_label": "Confirm & Book Appointment" if is_internal_admin else "Submit booking request",
        },
    )


@sensitive_post_parameters("code")
@never_cache
@require_http_methods(["GET", "POST"])
def verify(request):
    initial = {"reference": request.GET.get("reference", "")[:32]}
    form = BookingVerificationForm(request.POST if request.method == "POST" else None, initial=initial)
    if request.method == "POST" and form.is_valid():
        booking, token = verify_public_booking(
            form.cleaned_data["reference"], form.cleaned_data["code"], request
        )
        if booking and token:
            record_security_event(SecurityEvent.Action.BOOKING_VERIFIED, request=request, target=booking)
            return redirect("bookings:public_status", reference=booking.reference, token=token)
        record_security_event(
            SecurityEvent.Action.BOOKING_VERIFIED,
            request=request,
            target_type="bookings.Appointment",
            result=SecurityEvent.Result.FAILURE,
        )
        form.add_error(None, GENERIC_VERIFICATION_ERROR)
    return render(request, "bookings/verify.html", {"form": form})


@never_cache
@require_http_methods(["GET", "POST"])
def resend(request):
    form = BookingResendForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        resend_verification(form.cleaned_data["reference"], form.cleaned_data["email"], request)
        messages.success(
            request,
            "If the unverified booking is eligible, a new verification code has been sent.",
        )
        return redirect("bookings:verify")
    return render(request, "bookings/resend.html", {"form": form})


@sensitive_post_parameters("access_token")
@never_cache
@require_http_methods(["GET", "POST"])
def status_lookup(request):
    form = BookingLookupForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        booking = get_public_booking(form.cleaned_data["reference"], form.cleaned_data["access_token"])
        if booking:
            return redirect(
                "bookings:public_status",
                reference=booking.reference,
                token=form.cleaned_data["access_token"],
            )
        form.add_error(None, GENERIC_ACCESS_ERROR)
    return render(request, "bookings/status_lookup.html", {"form": form})


@never_cache
@require_http_methods(["GET"])
def public_status(request, reference, token):
    booking = get_public_booking(reference, token)
    if booking is None:
        return render(request, "bookings/access_invalid.html", status=404)
    return render(request, "bookings/status.html", {"booking": booking, "access_token": token})


@never_cache
@require_http_methods(["GET", "POST"])
def cancel(request, reference, token):
    booking = get_public_booking(reference, token)
    if booking is None:
        return render(request, "bookings/access_invalid.html", status=404)
    form = BookingCancellationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        if cancel_public_booking(reference, token) is None:
            return render(request, "bookings/access_invalid.html", status=404)
        messages.success(request, "The booking was cancelled.")
        return redirect("bookings:public_status", reference=reference, token=token)
    return render(
        request,
        "bookings/cancel.html",
        {"booking": booking, "access_token": token, "form": form},
    )


@never_cache
@require_http_methods(["GET", "POST"])
def reschedule(request, reference, token):
    booking = get_public_booking(reference, token)
    if booking is None:
        return render(request, "bookings/access_invalid.html", status=404)
    form = BookingRescheduleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            updated = reschedule_public_booking(
                reference, token, form.cleaned_data["scheduled_for"]
            )
        except ValidationError as exc:
            form.add_error("scheduled_for", "; ".join(exc.messages))
        else:
            if updated is None:
                return render(request, "bookings/access_invalid.html", status=404)
            messages.success(request, "The booking was rescheduled and is pending approval.")
            return redirect("bookings:public_status", reference=reference, token=token)
    return render(
        request,
        "bookings/reschedule.html",
        {"booking": booking, "access_token": token, "form": form},
    )


def _filtered_appointments(request, queryset):
    form = AppointmentFilterForm(request.GET or None)
    if form.is_valid():
        search_query = form.cleaned_data.get("search")
        if search_query:
            from django.db.models import Q
            q_term = search_query.strip()
            queryset = queryset.filter(
                Q(booking_reference__icontains=q_term)
                | Q(customer_name_snapshot__icontains=q_term)
                | Q(customer_email_snapshot__icontains=q_term)
                | Q(customer_phone_snapshot__icontains=q_term)
                | Q(notes__icontains=q_term)
            )
        if form.cleaned_data.get("date"):
            queryset = queryset.filter(appointment_date=form.cleaned_data["date"])
        if form.cleaned_data.get("status"):
            queryset = queryset.filter(status=form.cleaned_data["status"])
        if form.cleaned_data.get("staff"):
            queryset = queryset.filter(assigned_staff=form.cleaned_data["staff"])
        if form.cleaned_data.get("source"):
            queryset = queryset.filter(booking_source=form.cleaned_data["source"])
        sort_by = form.cleaned_data.get("sort")
        if sort_by:
            queryset = queryset.order_by(sort_by)
        else:
            queryset = queryset.order_by("-appointment_date", "-start_time")
    else:
        queryset = queryset.order_by("-appointment_date", "-start_time")
    return queryset.select_related("customer", "assigned_staff").prefetch_related(
        "appointment_services"
    ), form


@capability_required(CAPABILITY_MANAGE_BOOKINGS)
def manage(request):
    appointments, form = _filtered_appointments(
        request, Appointment.objects.visible_to(request.user)
    )

    # Export to CSV feature (Filter, sort, export and search)
    if request.GET.get("export") == "csv":
        import csv
        from django.http import HttpResponse

        today_str = timezone.localdate().strftime("%Y-%m-%d")
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="appointments_export_{today_str}.csv"'

        writer = csv.writer(response)
        writer.writerow([
            "Reference",
            "Customer Name",
            "Email",
            "Phone",
            "Appointment Date",
            "Start Time",
            "End Time",
            "Assigned Staff",
            "Booking Source",
            "Status",
            "Services",
            "Total Price (PHP)",
            "Notes / Consultation",
        ])

        for appt in appointments:
            service_names = ", ".join(
                item.service_name_snapshot for item in appt.appointment_services.all()
            )
            total_price = sum(item.price_snapshot for item in appt.appointment_services.all())
            staff_name = (
                appt.assigned_staff.get_full_name() if appt.assigned_staff else "Unassigned"
            )
            clean_notes = appt.notes.replace("\n", " | ").replace("\r", "") if appt.notes else ""
            writer.writerow([
                appt.reference,
                appt.customer_name,
                appt.customer_email_snapshot,
                appt.customer_phone_snapshot,
                str(appt.appointment_date),
                str(appt.start_time),
                str(appt.end_time or ""),
                staff_name,
                appt.get_booking_source_display(),
                appt.get_status_display(),
                service_names,
                f"{total_price:.2f}",
                clean_notes,
            ])
        return response

    legacy_bookings = Booking.objects.visible_to(request.user)
    if form.is_valid():
        search_query = form.cleaned_data.get("search")
        if search_query:
            from django.db.models import Q
            q_term = search_query.strip()
            legacy_bookings = legacy_bookings.filter(
                Q(reference__icontains=q_term)
                | Q(customer_name__icontains=q_term)
                | Q(email__icontains=q_term)
                | Q(phone_number__icontains=q_term)
            )
        if form.cleaned_data.get("date"):
            legacy_bookings = legacy_bookings.filter(
                scheduled_for__date=form.cleaned_data["date"]
            )
        if form.cleaned_data.get("staff"):
            legacy_bookings = legacy_bookings.filter(
                assigned_staff=form.cleaned_data["staff"]
            )
    bookings = [*appointments, *legacy_bookings.select_related("assigned_staff")]
    return render(
        request,
        "bookings/internal_list.html",
        {"bookings": bookings, "heading": "Appointment Management", "filter_form": form},
    )


@capability_required(CAPABILITY_MANAGE_BOOKINGS)
def calendar(request):
    appointments, form = _filtered_appointments(
        request, Appointment.objects.visible_to(request.user)
    )
    return render(
        request,
        "bookings/calendar.html",
        {"appointments": appointments, "filter_form": form},
    )


@staff_required
def assigned(request):
    appointments, form = _filtered_appointments(
        request, Appointment.objects.assigned_to(request.user)
    )
    return render(
        request,
        "bookings/internal_list.html",
        {"bookings": appointments, "heading": "Assigned Appointments", "filter_form": form},
    )


@authenticated_internal_user_required
@require_http_methods(["GET", "POST"])
def detail(request, reference):
    appointment = get_object_or_404(
        Appointment.objects.visible_to(request.user)
        .select_related("customer", "assigned_staff")
        .prefetch_related("appointment_services", "status_history__actor"),
        booking_reference=reference,
    )
    status_data = request.POST if request.method == "POST" and request.POST.get("action") == "status" else None
    form = AppointmentStatusForm(
        status_data,
        appointment=appointment,
        actor=request.user,
    )
    can_manage_schedule = request.user.is_owner or request.user.is_cashier
    schedule_data = (
        request.POST
        if request.method == "POST" and request.POST.get("action") == "schedule"
        else None
    )
    schedule_form = (
        AppointmentScheduleForm(schedule_data, instance=appointment)
        if can_manage_schedule
        else None
    )
    if status_data is not None and form.is_valid():
        try:
            transition_appointment(
                appointment, form.cleaned_data["status"], request.user, form.cleaned_data["note"]
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Appointment status updated.")
            return redirect("bookings:detail", reference=reference)

    if request.method == "POST" and request.POST.get("action") == "consultation":
        tech_notes = request.POST.get("technician_notes", "").strip()
        if tech_notes:
            stamp = timezone.localtime().strftime("%b %d, %Y %I:%M %p")
            staff_name = request.user.get_full_name() or request.user.email
            addition = f"\n[Technician Consultation Assessment ({stamp} by {staff_name})]:\n{tech_notes}"
            appointment.notes = (appointment.notes + addition).strip()
            appointment.save(update_fields=["notes", "updated_at"])
            messages.success(request, "Technician consultation assessment recorded successfully.")
            return redirect("bookings:detail", reference=reference)

    if schedule_data is not None and schedule_form.is_valid():
        try:
            update_appointment_schedule(
                appointment,
                appointment_date=schedule_form.cleaned_data["appointment_date"],
                start_time=schedule_form.cleaned_data["start_time"],
                assigned_staff=schedule_form.cleaned_data["assigned_staff"],
                actor=request.user,
            )
        except ValidationError as exc:
            schedule_form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Appointment schedule and assignment updated.")
            return redirect("bookings:detail", reference=reference)
    return render(
        request,
        "bookings/detail.html",
        {"appointment": appointment, "form": form, "schedule_form": schedule_form},
    )
