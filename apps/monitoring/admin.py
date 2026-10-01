from django.contrib import admin

from .models import ServiceStatusHistory


@admin.register(ServiceStatusHistory)
class ServiceStatusHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp",
        "appointment_service",
        "old_status",
        "new_status",
        "user",
    )
    list_filter = ("old_status", "new_status", "timestamp")
    search_fields = (
        "appointment_service__service_name",
        "appointment_service__appointment__booking_reference",
        "user__email",
        "note",
    )
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
