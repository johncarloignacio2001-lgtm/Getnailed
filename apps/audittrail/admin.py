from django.contrib import admin

from .models import AuditLog, SecurityEvent


class OwnerReadOnlyAdmin(admin.ModelAdmin):
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


@admin.register(AuditLog)
class AuditLogAdmin(OwnerReadOnlyAdmin):
    list_display = ('created_at', 'user', 'method', 'path', 'status_code', 'ip_address')
    list_filter = ('method', 'status_code', 'created_at')
    search_fields = ('user__username', 'path', 'ip_address')



@admin.register(SecurityEvent)
class SecurityEventAdmin(OwnerReadOnlyAdmin):
    list_display = (
        'created_at',
        'action',
        'result',
        'user',
        'target_type',
        'target_id',
        'ip_address',
        'request_id',
    )
    list_filter = ('action', 'result', 'created_at')
    search_fields = ('user__email', 'target_type', 'target_id', 'ip_address', 'request_id')
