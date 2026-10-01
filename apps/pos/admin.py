from django.contrib import admin

from .models import Payment, ReceiptSequence, Sale, SaleItem


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
        "total",
        "status",
        "created_at",
    )
    list_filter = ("status", "discount_type", "created_at")
    search_fields = ("receipt_number", "customer_name_snapshot", "cashier_name_snapshot")
    inlines = (SaleItemInline, PaymentInline)
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


@admin.register(ReceiptSequence)
class ReceiptSequenceAdmin(admin.ModelAdmin):
    readonly_fields = ("last_value", "updated_at")
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
