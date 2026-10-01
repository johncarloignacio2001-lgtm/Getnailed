from django.contrib import admin

from .models import Service, ServiceCategory, StaffProfile


class OwnerOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_module_permission(self, request):
        return request.user.is_authenticated and request.user.is_owner

    def has_view_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

    def has_add_permission(self, request):
        return request.user.is_authenticated and request.user.is_owner

    def has_change_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

    def has_delete_permission(self, request, obj=None):
        # Sensitive deletion is available through the reauthentication-protected app views.
        return False


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(OwnerOnlyAdmin):
    list_display = ("name", "service_count", "updated_at")
    search_fields = ("name", "description")

    @admin.display(description="Services")
    def service_count(self, obj):
        return obj.services.count()


@admin.register(Service)
class ServiceAdmin(OwnerOnlyAdmin):
    list_display = ("name", "category", "duration_minutes", "price", "is_active")
    list_filter = ("is_active", "category")
    search_fields = ("name", "description", "category__name")
    list_select_related = ("category",)


@admin.register(StaffProfile)
class StaffProfileAdmin(OwnerOnlyAdmin):
    list_display = ("user", "specialty", "availability_status", "is_active")
    list_filter = ("availability_status", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name", "specialty")
    list_select_related = ("user",)
