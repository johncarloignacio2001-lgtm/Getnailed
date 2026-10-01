from django.contrib import admin

from .models import ForecastResult, ForecastRun


class ForecastResultInline(admin.TabularInline):
    model = ForecastResult
    extra = 0
    can_delete = False
    readonly_fields = (
        "forecast_date",
        "service_category",
        "predicted_sales",
        "lower_bound",
        "upper_bound",
        "generated_at",
    )


@admin.register(ForecastRun)
class ForecastRunAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "public_id",
        "status",
        "training_start",
        "training_end",
        "sample_count",
        "mae",
        "rmse",
    )
    list_filter = ("status", "created_at")
    search_fields = ("public_id", "message", "trained_by__email")
    inlines = (ForecastResultInline,)
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
