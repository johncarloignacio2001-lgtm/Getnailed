from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import admin
from django.db import models
from django.utils import timezone

from apps.accounts.models import User
from .models import Appointment, AppointmentService, AppointmentStatusHistory, Booking


class UnassignedTechnicianFilter(admin.SimpleListFilter):
    title = "Technician Assignment"
    parameter_name = "technician_status"

    def lookups(self, request, model_admin):
        return (
            ("assigned", "Assigned to Technician"),
            ("unassigned", "Unassigned (Needs Technician)"),
        )

    def queryset(self, request, queryset):
        if self.value() == "assigned":
            return queryset.filter(assigned_staff__isnull=False)
        elif self.value() == "unassigned":
            return queryset.filter(assigned_staff__isnull=True)
        return queryset


class AppointmentAdminForm(forms.ModelForm):
    customer_name_snapshot = forms.CharField(
        required=False,
        label="Customer Name Snapshot",
        help_text="Leave blank to auto-fill from selected Customer.",
    )
    customer_email_snapshot = forms.EmailField(
        required=False,
        label="Customer Email Snapshot",
        help_text="Leave blank to auto-fill from selected Customer.",
    )
    customer_phone_snapshot = forms.CharField(
        required=False,
        label="Customer Phone Snapshot",
        help_text="Leave blank to auto-fill from selected Customer.",
    )

    class Meta:
        model = Appointment
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "assigned_staff" in self.fields:
            self.fields["assigned_staff"].queryset = User.objects.filter(
                role=User.Role.STAFF,
                is_active=True,
                is_active_staff_member=True,
            ).select_related("staff_profile").order_by("first_name", "last_name", "email")
            self.fields["assigned_staff"].label_from_instance = (
                lambda u: f"{u.get_full_name()} — {u.staff_profile.specialty}"
                if getattr(u, "staff_profile", None) and u.staff_profile.specialty
                else u.get_full_name() or u.email
            )
            self.fields["assigned_staff"].empty_label = "Unassigned (Select technician)"

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get("customer")
        if customer:
            if not cleaned_data.get("customer_name_snapshot"):
                cleaned_data["customer_name_snapshot"] = customer.full_name
            if not cleaned_data.get("customer_email_snapshot") and customer.email:
                cleaned_data["customer_email_snapshot"] = customer.email
            if not cleaned_data.get("customer_phone_snapshot") and customer.phone:
                cleaned_data["customer_phone_snapshot"] = customer.phone

        if not cleaned_data.get("customer_name_snapshot") and not customer:
            self.add_error("customer", "Please select a customer or provide a customer name.")

        return cleaned_data


class AppointmentServiceInline(admin.TabularInline):
    model = AppointmentService
    extra = 1
    can_delete = True
    fields = (
        "service",
        "assigned_staff",
        "service_name",
        "duration_minutes",
        "price",
        "status",
        "position",
    )

    def has_add_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form
        for fname in ("service_name", "duration_minutes", "price"):
            if fname in form.base_fields:
                form.base_fields[fname].required = False
                form.base_fields[fname].help_text = "Auto-filled from Service if blank"
        if "assigned_staff" in form.base_fields:
            form.base_fields["assigned_staff"].queryset = User.objects.filter(
                role=User.Role.STAFF,
                is_active=True,
            ).select_related("staff_profile").order_by("first_name", "last_name")
            form.base_fields["assigned_staff"].label_from_instance = (
                lambda u: f"{u.get_full_name()} — {u.staff_profile.specialty}"
                if getattr(u, "staff_profile", None) and u.staff_profile.specialty
                else u.get_full_name() or u.email
            )
            form.base_fields["assigned_staff"].empty_label = "Inherit Appointment Technician"
        return formset


class AppointmentStatusHistoryInline(admin.TabularInline):
    model = AppointmentStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")
    fields = ("from_status", "to_status", "actor", "note", "created_at")

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    form = AppointmentAdminForm
    list_display = (
        "booking_reference",
        "customer_name_snapshot",
        "appointment_date",
        "time_slot_display",
        "assigned_staff",
        "services_display",
        "total_amount_display",
        "status",
        "booking_source",
    )
    list_editable = ("assigned_staff", "status")
    list_filter = (
        UnassignedTechnicianFilter,
        "status",
        "assigned_staff",
        "booking_source",
        "appointment_date",
    )
    date_hierarchy = "appointment_date"
    search_fields = (
        "booking_reference",
        "customer_name_snapshot",
        "customer_email_snapshot",
    )
    list_select_related = ("customer", "assigned_staff")
    readonly_fields = ("booking_reference", "created_at", "updated_at")
    inlines = (AppointmentServiceInline, AppointmentStatusHistoryInline)
    actions = (
        "action_mark_approved",
        "action_mark_completed",
        "action_mark_cancelled",
    )

    fieldsets = (
        (
            "Booking Info",
            {
                "fields": (
                    "booking_reference",
                    "status",
                    "booking_source",
                    "created_by",
                )
            },
        ),
        (
            "Customer Details",
            {
                "fields": (
                    "customer",
                    "customer_name_snapshot",
                    "customer_email_snapshot",
                    "customer_phone_snapshot",
                )
            },
        ),
        (
            "Technician & Schedule",
            {
                "fields": (
                    "assigned_staff",
                    "appointment_date",
                    "start_time",
                    "end_time",
                )
            },
        ),
        (
            "Notes & Details",
            {
                "fields": (
                    "notes",
                    "cancellation_reason",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(description="Time Window")
    def time_slot_display(self, obj):
        start = obj.start_time.strftime("%I:%M %p") if obj.start_time else ""
        end = obj.end_time.strftime("%I:%M %p") if obj.end_time else ""
        if start and end:
            return f"{start} - {end}"
        return start or "—"

    @admin.display(description="Services")
    def services_display(self, obj):
        services = list(obj.appointment_services.values_list("service_name", flat=True))
        if services:
            names = ", ".join(services)
            return (names[:40] + "...") if len(names) > 40 else names
        return "—"

    @admin.display(description="Total Price")
    def total_amount_display(self, obj):
        return f"₱{obj.total_price:,.2f}"

    @admin.action(description="Mark selected appointments as Approved")
    def action_mark_approved(self, request, queryset):
        count = queryset.update(status=Appointment.Status.APPROVED)
        self.message_user(request, f"{count} appointment(s) marked as Approved.")

    @admin.action(description="Mark selected appointments as Completed")
    def action_mark_completed(self, request, queryset):
        count = queryset.update(status=Appointment.Status.COMPLETED)
        self.message_user(request, f"{count} appointment(s) marked as Completed.")

    @admin.action(description="Mark selected appointments as Cancelled")
    def action_mark_cancelled(self, request, queryset):
        count = queryset.update(status=Appointment.Status.CANCELLED)
        self.message_user(request, f"{count} appointment(s) marked as Cancelled.")

    def has_module_permission(self, request):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_add_permission(self, request):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser
        )

    def save_model(self, request, obj, form, change):
        if not obj.expires_at:
            obj.expires_at = timezone.now() + timedelta(days=365)
        if not obj.created_by:
            obj.created_by = request.user
        if obj.customer:
            if not obj.customer_name_snapshot:
                obj.customer_name_snapshot = obj.customer.full_name
            if not obj.customer_email_snapshot:
                obj.customer_email_snapshot = obj.customer.email or ""
            if not obj.customer_phone_snapshot:
                obj.customer_phone_snapshot = obj.customer.phone or ""

        # Track status & staff changes
        previous_status = None
        previous_staff_id = None
        if change and obj.pk:
            orig = Appointment.objects.filter(pk=obj.pk).values("status", "assigned_staff_id").first()
            if orig:
                previous_status = orig["status"]
                previous_staff_id = orig["assigned_staff_id"]

        super().save_model(request, obj, form, change)

        # Sync assigned technician to all service items if set or changed
        if obj.assigned_staff:
            obj.appointment_services.filter(
                models.Q(assigned_staff__isnull=True) | models.Q(assigned_staff_id=previous_staff_id)
            ).update(assigned_staff=obj.assigned_staff)

        actor = request.user
        if previous_status and previous_status != obj.status:
            AppointmentStatusHistory.objects.create(
                appointment=obj,
                from_status=previous_status,
                to_status=obj.status,
                actor=actor,
                note=f"Status changed in admin to {obj.get_status_display()} by {actor}",
            )

        if change and previous_staff_id != obj.assigned_staff_id:
            staff_name = obj.assigned_staff.get_full_name() if obj.assigned_staff else "Unassigned"
            AppointmentStatusHistory.objects.create(
                appointment=obj,
                from_status=obj.status,
                to_status=obj.status,
                actor=actor,
                note=f"Technician assigned to {staff_name} in admin by {actor}",
            )
            if obj.assigned_staff:
                from apps.notifications.models import Notification
                Notification.objects.create(
                    recipient=obj.assigned_staff,
                    appointment=obj,
                    event_type=Notification.EventType.NEW,
                    title="New appointment assigned",
                    message=f"You have been assigned to appointment #{obj.booking_reference} on {obj.appointment_date}.",
                )

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        obj = form.instance
        for index, instance in enumerate(instances):
            if isinstance(instance, AppointmentService):
                if not instance.appointment_id:
                    instance.appointment = obj
                if instance.service:
                    if not instance.service_name:
                        instance.service_name = instance.service.name
                    if instance.duration_minutes is None:
                        instance.duration_minutes = instance.service.duration_minutes
                    if instance.price is None:
                        instance.price = instance.service.price
                if not instance.assigned_staff and obj.assigned_staff:
                    instance.assigned_staff = obj.assigned_staff
                if instance.position == 0:
                    instance.position = index
                instance.save()
        for deleted in formset.deleted_objects:
            deleted.delete()
        formset.save_m2m()

        # Recalculate end_time if start_time is set
        total_duration = obj.total_duration_minutes
        if total_duration > 0 and obj.start_time:
            from apps.bookings.services import _appointment_end
            new_end = _appointment_end(obj.appointment_date, obj.start_time, total_duration)
            if obj.end_time != new_end:
                obj.end_time = new_end
                Appointment.objects.filter(pk=obj.pk).update(end_time=new_end)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        obj = form.instance
        if obj.assigned_staff:
            obj.appointment_services.filter(assigned_staff__isnull=True).update(
                assigned_staff=obj.assigned_staff
            )


@admin.register(Booking)
class LegacyBookingAdmin(admin.ModelAdmin):
    list_display = (
        "reference",
        "customer_name",
        "email",
        "service_name",
        "scheduled_for",
        "assigned_staff",
        "status",
    )
    list_filter = ("status", "assigned_staff", "scheduled_for")
    search_fields = ("reference", "customer_name", "email")
    readonly_fields = ("reference", "created_at", "updated_at")

    def has_module_permission(self, request):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser
        )

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser
        )


@admin.register(AppointmentStatusHistory)
class AppointmentStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ("appointment", "from_status", "to_status", "actor", "created_at")
    list_filter = ("from_status", "to_status", "created_at")
    search_fields = ("appointment__booking_reference", "actor__email", "note")
    readonly_fields = ("appointment", "from_status", "to_status", "actor", "note", "created_at")

    def has_module_permission(self, request):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and (
            request.user.is_owner or request.user.is_superuser or request.user.is_staff
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
