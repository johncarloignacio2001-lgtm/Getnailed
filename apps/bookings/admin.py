from django.contrib import admin

from .models import Appointment, AppointmentService


class AppointmentServiceInline(admin.TabularInline):
    model = AppointmentService
    extra = 0
    can_delete = False
    readonly_fields = ("service", "service_name", "duration_minutes", "price", "position")


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = (
        "booking_reference",
        "customer_name_snapshot",
        "appointment_date",
        "start_time",
        "assigned_staff",
        "status",
    )
    list_filter = ("status", "booking_source", "appointment_date")
    search_fields = (
        "booking_reference",
        "customer_name_snapshot",
        "customer_email_snapshot",
    )
    list_select_related = ("customer", "assigned_staff")
    inlines = (AppointmentServiceInline,)
    actions = None

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.is_owner

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
