from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        (
            'Get Nailed Access',
            {
                'fields': (
                    'role',
                    'phone_number',
                    'is_active_staff_member',
                    'email_verified_at',
                    'is_locked',
                    'can_use_pos',
                    'can_manage_bookings',
                    'can_manage_customers',
                    'can_assign_services',
                )
            },
        ),
    )
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active', 'is_locked')
    list_filter = ('role', 'is_active', 'is_locked', 'is_staff')
    ordering = ('email',)

    def has_add_permission(self, request):
        # Internal users must be created through the invitation workflow.
        return False

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.is_owner

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner
