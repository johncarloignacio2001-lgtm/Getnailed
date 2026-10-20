import calendar
from datetime import time, timedelta

from django.contrib import admin
from django.db import models
from django.utils import timezone

from .models import Payment, ReceiptSequence, Sale, SaleItem


class SaleTimePeriodFilter(admin.SimpleListFilter):
    title = "Time Period"
    parameter_name = "time_period"

    def lookups(self, request, model_admin):
        return (
            ("today", "Today"),
            ("yesterday", "Yesterday"),
            ("this_week", "This Week"),
            ("this_month", "This Month"),
            ("last_month", "Last Month"),
            ("morning", "Morning (Opening - 12:00 PM)"),
            ("afternoon", "Afternoon (12:00 PM - 5:00 PM)"),
            ("evening", "Evening (5:00 PM - Closing)"),
        )

    def queryset(self, request, queryset):
        today = timezone.localdate()
        val = self.value()
        if val == "today":
            return queryset.filter(created_at__date=today)
        elif val == "yesterday":
            return queryset.filter(created_at__date=today - timedelta(days=1))
        elif val == "this_week":
            start_date = today - timedelta(days=today.weekday())
            return queryset.filter(
                created_at__date__gte=start_date,
                created_at__date__lte=start_date + timedelta(days=6),
            )
        elif val == "this_month":
            return queryset.filter(created_at__year=today.year, created_at__month=today.month)
        elif val == "last_month":
            first_of_this_month = today.replace(day=1)
            last_of_prev_month = first_of_this_month - timedelta(days=1)
            return queryset.filter(
                created_at__year=last_of_prev_month.year,
                created_at__month=last_of_prev_month.month,
            )
        elif val == "morning":
            return queryset.filter(created_at__time__lt=time(12, 0))
        elif val == "afternoon":
            return queryset.filter(
                created_at__time__gte=time(12, 0),
                created_at__time__lt=time(17, 0),
            )
        elif val == "evening":
            return queryset.filter(created_at__time__gte=time(17, 0))
        return queryset


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    can_delete = False
    readonly_fields = (
        "service",
        "assigned_staff",
        "service_name",
        "service_category",
        "staff_name",
        "unit_price",
        "quantity",
        "line_total",
        "position",
    )


class PaymentInline(admin.StackedInline):
    model = Payment
    extra = 0
    can_delete = False
    readonly_fields = (
        "payment_method",
        "amount_tendered",
        "change",
        "reference",
        "recorded_by",
        "created_at",
    )


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = (
        "receipt_number",
        "customer_name_snapshot",
        "cashier_name_snapshot",
        "total_display",
        "items_count_display",
        "payment_method_display",
        "status",
        "created_at_display",
    )
    list_filter = (
        SaleTimePeriodFilter,
        "status",
        "discount_type",
        "created_at",
    )
    date_hierarchy = "created_at"
    search_fields = ("receipt_number", "customer_name_snapshot", "cashier_name_snapshot")
    inlines = (SaleItemInline, PaymentInline)
    actions = None

    @admin.display(description="Total", ordering="total")
    def total_display(self, obj):
        return f"₱{obj.total:,.2f}"

    @admin.display(description="Items")
    def items_count_display(self, obj):
        count = obj.items.count()
        return f"{count} item{'s' if count != 1 else ''}"

    @admin.display(description="Payment Method")
    def payment_method_display(self, obj):
        if hasattr(obj, "payment") and obj.payment:
            return obj.payment.get_payment_method_display()
        return "—"

    @admin.display(description="Date & Time", ordering="created_at")
    def created_at_display(self, obj):
        return obj.created_at.strftime("%b %d, %Y %I:%M %p")

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


@admin.register(ReceiptSequence)
class ReceiptSequenceAdmin(admin.ModelAdmin):
    readonly_fields = ("last_value", "updated_at")
    actions = None

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
