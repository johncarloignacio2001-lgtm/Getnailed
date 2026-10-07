from django.contrib import admin

from .models import (
    Service,
    ServiceCategory,
    StaffProfile,
    StaffSchedule,
    StaffTimeBlock,
)


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


@admin.register(StaffTimeBlock)
class StaffTimeBlockAdmin(OwnerOnlyAdmin):
    list_display = ("staff", "date", "start_time", "end_time", "reason", "created_at")
    list_filter = ("date", "staff")
    search_fields = ("staff__first_name", "staff__last_name", "staff__email", "reason")
    ordering = ("-date", "start_time")
    list_select_related = ("staff",)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner


@admin.register(StaffSchedule)
class StaffScheduleAdmin(OwnerOnlyAdmin):
    list_display = (
        "staff",
        "day_of_week",
        "start_time",
        "end_time",
        "lunch_break_display",
        "is_working",
    )
    list_filter = ("day_of_week", "is_working", "staff")
    search_fields = ("staff__first_name", "staff__last_name", "staff__email")
    ordering = ("staff", "day_of_week")
    list_select_related = ("staff",)

    @admin.display(description="Lunch Break")
    def lunch_break_display(self, obj):
        if not obj.is_working:
            return "Day Off"
        if obj.lunch_start and obj.lunch_end:
            return f"{obj.lunch_start.strftime('%I:%M %p')} - {obj.lunch_end.strftime('%I:%M %p')}"
        return "-"

    def has_delete_permission(self, request, obj=None):
        return request.user.is_authenticated and request.user.is_owner

