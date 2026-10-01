from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class ReceiptSequence(models.Model):
    last_value = models.PositiveBigIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "receipt sequence"

    def __str__(self):
        return f"Receipt sequence {self.last_value}"


class SaleQuerySet(models.QuerySet):
    def completed(self):
        return self.filter(status=Sale.Status.COMPLETED)

    def visible_to(self, user):
        if user.is_authenticated and user.is_owner:
            return self
        if user.is_authenticated and (user.is_cashier or user.can_use_pos):
            return self.filter(cashier=user)
        return self.none()


class Sale(models.Model):
    class DiscountType(models.TextChoices):
        NONE = "NONE", "No discount"
        FIXED = "FIXED", "Fixed amount"
        PERCENT = "PERCENT", "Percentage"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOIDED = "VOIDED", "Voided"

    receipt_number = models.CharField(max_length=32, unique=True, editable=False)
    customer = models.ForeignKey(
        "customers.Customer",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sales",
    )
    customer_name_snapshot = models.CharField(max_length=201, default="Walk-in customer")
    appointment = models.OneToOneField(
        "bookings.Appointment",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sale",
    )
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.NONE,
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    total = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.COMPLETED,
    )
    void_reason = models.CharField(max_length=500, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="voided_sales",
    )
    voided_at = models.DateTimeField(blank=True, null=True)
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="processed_sales",
    )
    cashier_name_snapshot = models.CharField(max_length=201)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SaleQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [
            models.Index(fields=("status", "created_at"), name="sale_status_created_idx"),
            models.Index(fields=("cashier", "created_at"), name="sale_cashier_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subtotal__gte=Decimal("0.00")),
                name="sale_subtotal_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_value__gte=Decimal("0.00")),
                name="sale_discount_value_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__gte=Decimal("0.00"))
                & models.Q(discount_amount__lte=models.F("subtotal")),
                name="sale_discount_amount_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(total__gte=Decimal("0.00")),
                name="sale_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    total=models.F("subtotal") - models.F("discount_amount")
                ),
                name="sale_total_matches_components",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_type__in=("NONE", "FIXED", "PERCENT")),
                name="sale_discount_type_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=("COMPLETED", "VOIDED")),
                name="sale_status_valid",
            ),
            models.CheckConstraint(
                condition=~models.Q(status="VOIDED")
                | (
                    ~models.Q(void_reason="")
                    & models.Q(voided_by__isnull=False)
                    & models.Q(voided_at__isnull=False)
                ),
                name="voided_sale_has_metadata",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            original = type(self).objects.filter(pk=self.pk).values_list(
                "receipt_number", flat=True
            ).first()
            if original is not None and original != self.receipt_number:
                raise ValidationError("Receipt numbers are immutable.")
        super().save(*args, **kwargs)

    @property
    def amount_tendered(self):
        return self.payment.amount_tendered

    @property
    def change(self):
        return self.payment.change

    @property
    def payment_method(self):
        return self.payment.payment_method

    def __str__(self):
        return self.receipt_number


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    service = models.ForeignKey(
        "services.Service",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sale_items",
    )
    assigned_staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sale_items",
        limit_choices_to={"role": "STAFF"},
    )
    service_name = models.CharField(max_length=160)
    service_category = models.CharField(max_length=100, default="Uncategorized")
    staff_name = models.CharField(max_length=201, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveSmallIntegerField(
        default=1,
        validators=(MinValueValidator(1), MaxValueValidator(100)),
    )
    line_total = models.DecimalField(max_digits=12, decimal_places=2)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("sale", "position"),
                name="sale_item_position_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=100),
                name="sale_item_quantity_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price__gte=Decimal("0.00")),
                name="sale_item_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total__gte=Decimal("0.00")),
                name="sale_item_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    line_total=models.F("unit_price") * models.F("quantity")
                ),
                name="sale_item_total_matches_components",
            ),
        ]

    def __str__(self):
        return f"{self.service_name} x {self.quantity}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Cash"
        CARD = "CARD", "Card"
        GCASH = "GCASH", "GCash"
        MAYA = "MAYA", "Maya"
        BANK = "BANK", "Bank transfer"

    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name="payment")
    payment_method = models.CharField(max_length=12, choices=Method.choices)
    amount_tendered = models.DecimalField(max_digits=12, decimal_places=2)
    change = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_payments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_tendered__gte=Decimal("0.00")),
                name="payment_tendered_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(change__gte=Decimal("0.00")),
                name="payment_change_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    payment_method__in=("CASH", "CARD", "GCASH", "MAYA", "BANK")
                ),
                name="payment_method_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(payment_method="CASH")
                | models.Q(change=Decimal("0.00")),
                name="noncash_payment_has_no_change",
            ),
        ]

    def __str__(self):
        return f"{self.sale} - {self.get_payment_method_display()}"
