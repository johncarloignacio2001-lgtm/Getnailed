from django.contrib import admin

from .models import Customer


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "email", "phone", "user", "updated_at")
    search_fields = ("first_name", "last_name", "email", "phone")
    list_filter = ("user",)
    autocomplete_fields = ("user",)
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
        return False
