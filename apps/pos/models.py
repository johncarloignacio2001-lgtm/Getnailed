from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class PromoVoucher(models.Model):
    class DiscountType(models.TextChoices):
        PERCENT = "PERCENT", "Percentage"
        FIXED = "FIXED", "Fixed amount"

    code = models.CharField(max_length=50, unique=True)
    description = models.CharField(max_length=255, blank=True)
    discount_type = models.CharField(
        max_length=10,
        choices=DiscountType.choices,
        default=DiscountType.PERCENT,
    )
    discount_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=(MinValueValidator(Decimal("0.01")),),
    )
    max_discount_cap = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Maximum discount amount in PHP (capping rule).",
    )
    min_spend = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=(MinValueValidator(Decimal("0.00")),),
    )
    valid_from = models.DateField(default=timezone.localdate)
    valid_until = models.DateField(blank=True, null=True)
    usage_limit = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="Maximum total times this voucher may be claimed.",
    )
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def is_valid_for(self, subtotal, check_date=None):
        if not self.is_active:
            return False, "This voucher is inactive."
        check_date = check_date or timezone.localdate()
        if self.valid_from and check_date < self.valid_from:
            return False, "This voucher is not yet active."
        if self.valid_until and check_date > self.valid_until:
            return False, "This voucher has expired."
        if self.usage_limit is not None and self.times_used >= self.usage_limit:
            return False, "This voucher has reached its redemption limit."
        if subtotal < self.min_spend:
            return False, f"Minimum spend of ₱{self.min_spend} required for this voucher."
        return True, "Valid"

    def calculate_discount(self, subtotal):
        if self.discount_type == self.DiscountType.PERCENT:
            raw = (subtotal * self.discount_value) / Decimal("100.00")
        else:
            raw = self.discount_value
        if self.max_discount_cap is not None and self.max_discount_cap > Decimal("0.00"):
            raw = min(raw, self.max_discount_cap)
        return min(raw, subtotal)

    def __str__(self):
        return f"{self.code} ({self.get_discount_type_display()} {self.discount_value})"


class CashierShift(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        CLOSED = "CLOSED", "Closed"

    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="shifts",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(blank=True, null=True)
    opening_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=(MinValueValidator(Decimal("0.00")),),
        help_text="Starting cash drawer amount / till float.",
    )
    closing_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Actual physical cash counted at shift end.",
    )
    expected_cash = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Expected drawer total: opening_cash + cash_sales.",
    )
    cash_variance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Discrepancy (over/short): closing_cash - expected_cash.",
    )
    cash_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    ewallet_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    card_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    bank_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    total_sales = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    transaction_count = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
    )
    notes = models.TextField(blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="closed_shifts",
    )

    class Meta:
        ordering = ("-opened_at",)

    def reconcile(self, actual_closing_cash, closed_by_user=None, notes="", closed_by=None):
        from apps.pos.models import Payment, Sale
        closed_by_user = closed_by_user or closed_by
        shift_sales = self.sales.filter(status=Sale.Status.COMPLETED)
        self.transaction_count = shift_sales.count()
        self.total_sales = shift_sales.aggregate(s=models.Sum("total"))["s"] or Decimal("0.00")

        payments = Payment.objects.filter(sale__in=shift_sales)
        self.cash_sales = (
            payments.filter(payment_method=Payment.Method.CASH).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        self.ewallet_sales = (
            payments.filter(payment_method__in=[Payment.Method.GCASH, Payment.Method.MAYA]).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        self.card_sales = (
            payments.filter(payment_method=Payment.Method.CARD).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )
        self.bank_sales = (
            payments.filter(payment_method=Payment.Method.BANK).aggregate(
                s=models.Sum("sale__total")
            )["s"]
            or Decimal("0.00")
        )

        self.expected_cash = self.opening_cash + self.cash_sales
        self.closing_cash = Decimal(actual_closing_cash)
        self.cash_variance = self.closing_cash - self.expected_cash
        self.closed_at = timezone.now()
        self.status = self.Status.CLOSED
        self.closed_by = closed_by_user
        if notes:
            self.notes = notes
        self.save()

    def __str__(self):
        return f"Shift #{self.pk} - {self.cashier} ({self.get_status_display()})"


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
        SENIOR_CITIZEN = "SENIOR_CITIZEN", "Senior Citizen (20%)"
        PWD = "PWD", "PWD (20%)"
        PROMO_VOUCHER = "PROMO_VOUCHER", "Promo voucher"

    class Status(models.TextChoices):
        COMPLETED = "COMPLETED", "Completed"
        VOIDED = "VOIDED", "Voided"

    receipt_number = models.CharField(max_length=32, unique=True, editable=False)
    shift = models.ForeignKey(
        CashierShift,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sales",
    )
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
        max_length=20,
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
    discount_id_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Senior Citizen or PWD identification card number.",
    )
    discount_id_name = models.CharField(
        max_length=160,
        blank=True,
        help_text="Name printed on Senior Citizen or PWD ID.",
    )
    voucher = models.ForeignKey(
        PromoVoucher,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="sales",
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
                condition=models.Q(
                    discount_type__in=(
                        "NONE",
                        "FIXED",
                        "PERCENT",
                        "SENIOR_CITIZEN",
                        "PWD",
                        "PROMO_VOUCHER",
                    )
                ),
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
