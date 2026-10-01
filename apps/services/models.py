from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.models import User
from apps.core.upload_security import safe_image_upload_path, validate_image_upload


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("name",)
        verbose_name_plural = "service categories"
        constraints = [
            models.UniqueConstraint(
                Lower("name"),
                name="services_category_name_ci_unique",
            ),
        ]

    def __str__(self):
        return self.name


class Service(models.Model):
    name = models.CharField(max_length=160)
    category = models.ForeignKey(
        ServiceCategory,
        on_delete=models.PROTECT,
        related_name="services",
    )
    description = models.TextField(blank=True)
    duration_minutes = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(5), MaxValueValidator(480)),
    )
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=(
            MinValueValidator(Decimal("0.01")),
            MaxValueValidator(Decimal("999999.99")),
        ),
    )
    is_active = models.BooleanField(default=True)
    image = models.ImageField(
        upload_to=safe_image_upload_path,
        validators=(validate_image_upload,),
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("category__name", "name")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_minutes__gte=5, duration_minutes__lte=480),
                name="services_service_duration_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gt=Decimal("0.00")),
                name="services_service_price_positive",
            ),
            models.UniqueConstraint(
                models.F("category"),
                Lower("name"),
                name="services_service_category_name_ci_unique",
            ),
        ]

    def save(self, *args, **kwargs):
        new_image = bool(self.image and not self.image._committed)
        if new_image:
            validate_image_upload(self.image.file)
        try:
            super().save(*args, **kwargs)
        except Exception:
            if new_image and self.image and self.image._committed:
                self.image.storage.delete(self.image.name)
                self.image._committed = False
            raise

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        NOT_ACCEPTING = "NOT_ACCEPTING", "Not accepting appointments"
        ON_LEAVE = "ON_LEAVE", "On leave"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        limit_choices_to={"role": User.Role.STAFF},
    )
    specialty = models.CharField(max_length=160, blank=True)
    availability_status = models.CharField(
        max_length=20,
        choices=Availability.choices,
        default=Availability.AVAILABLE,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__first_name", "user__last_name", "user__email")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    availability_status__in=(
                        "AVAILABLE",
                        "NOT_ACCEPTING",
                        "ON_LEAVE",
                    )
                ),
                name="services_staff_availability_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.user_id and self.user.role != User.Role.STAFF:
            raise ValidationError({"user": "Staff profiles can only link to STAFF accounts."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.user)
