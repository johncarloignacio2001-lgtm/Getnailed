from django.contrib import admin

from django.db import models

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


class SpecialtyCategoryFilter(admin.SimpleListFilter):
    title = "Specialty"
    parameter_name = "specialty_group"

    def lookups(self, request, model_admin):
        return (
            ("NAIL TECH", "Nail Tech"),
            ("NAIL ART", "Nail Art"),
            ("LASH", "Lash Tech / Lash Lift"),
            ("WAX", "Wax / Threading"),
            ("THERAPIST", "Therapist"),
            ("FOOTSPA", "Foot Spa"),
            ("CASHIER", "Cashier"),
        )

    def queryset(self, request, queryset):
        val = self.value()
        if not val:
            return queryset
        if val == "CASHIER":
            return queryset.filter(models.Q(user__can_use_pos=True) | models.Q(specialty__icontains="Cashier"))
        elif val == "WAX":
            return queryset.filter(models.Q(specialty__icontains="Wax") | models.Q(specialty__icontains="Threading"))
        elif val == "LASH":
            return queryset.filter(models.Q(specialty__icontains="Lash"))
        elif val == "NAIL ART":
            return queryset.filter(models.Q(specialty__icontains="Nail Art"))
        elif val == "FOOTSPA":
            return queryset.filter(models.Q(specialty__icontains="Foot Spa") | models.Q(specialty__icontains="Footspa"))
        elif val == "THERAPIST":
            return queryset.filter(models.Q(specialty__icontains="Therapist"))
        elif val == "NAIL TECH":
            return queryset.filter(models.Q(specialty__icontains="Nail Tech") | models.Q(specialty__icontains="Nail Technician"))
        return queryset.filter(specialty__icontains=val)


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
    list_display = (
        "staff_name",
        "specialty",
        "qualified_services_count",
        "cashier_status",
        "availability_status",
        "is_active",
    )
    list_filter = (SpecialtyCategoryFilter, "availability_status", "is_active")
    search_fields = ("user__email", "user__first_name", "user__last_name", "specialty")
    filter_horizontal = ("skills",)
    list_select_related = ("user",)

    @admin.display(description="Staff Member", ordering="user__first_name")
    def staff_name(self, obj):
        name = obj.user.get_full_name()
        return f"{name} ({obj.user.email})" if name else obj.user.email

    @admin.display(description="Qualified Services")
    def qualified_services_count(self, obj):
        count = obj.skills.count()
        return f"{count} services" if count else "All services"

    @admin.display(description="Cashier", boolean=True)
    def cashier_status(self, obj):
        return obj.user.can_use_pos


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

