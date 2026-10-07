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

    @property
    def has_physical_inventory(self):
        """Services do not consume physical inventory. Their primary constraint is scheduled time blocks."""
        return False


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
    skills = models.ManyToManyField(
        Service,
        blank=True,
        related_name="qualified_technicians",
        help_text="Services this technician is trained and qualified to perform.",
    )
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

    def can_perform(self, service):
        """Check if technician has skill for this service. If technician has no specific skills assigned, they can perform all active services."""
        if not self.skills.exists():
            return True
        return self.skills.filter(pk=service.pk).exists()

    def __str__(self):
        return str(self.user)


class StaffSchedule(models.Model):
    class DayOfWeek(models.IntegerChoices):
        MONDAY = 0, "Monday"
        TUESDAY = 1, "Tuesday"
        WEDNESDAY = 2, "Wednesday"
        THURSDAY = 3, "Thursday"
        FRIDAY = 4, "Friday"
        SATURDAY = 5, "Saturday"
        SUNDAY = 6, "Sunday"

    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="schedules",
        limit_choices_to={"role": User.Role.STAFF},
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=DayOfWeek.choices,
        validators=(MinValueValidator(0), MaxValueValidator(6)),
    )
    start_time = models.TimeField(default="09:00:00")
    end_time = models.TimeField(default="18:00:00")
    lunch_start = models.TimeField(default="12:00:00", null=True, blank=True)
    lunch_end = models.TimeField(default="13:00:00", null=True, blank=True)
    is_working = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("staff", "day_of_week")
        constraints = [
            models.UniqueConstraint(
                fields=("staff", "day_of_week"),
                name="staff_schedule_day_unique",
            ),
        ]

    def clean(self):
        super().clean()
        if self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Shift end time must be after start time."})
        if self.lunch_start and self.lunch_end:
            if self.lunch_end <= self.lunch_start:
                raise ValidationError({"lunch_end": "Lunch break end time must be after start time."})
            if self.lunch_start < self.start_time or self.lunch_end > self.end_time:
                raise ValidationError({"lunch_start": "Lunch break must be within shift working hours."})

    def __str__(self):
        if not self.is_working:
            return f"{self.staff} - {self.get_day_of_week_display()}: Day Off / Leave"
        return f"{self.staff} - {self.get_day_of_week_display()}: {self.start_time}-{self.end_time}"


class StaffTimeBlock(models.Model):
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="time_blocks",
        limit_choices_to={"role": User.Role.STAFF},
    )
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    reason = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "start_time")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="staff_time_block_end_after_start",
            ),
        ]

    def clean(self):
        super().clean()
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValidationError({"end_time": "Block end time must be after start time."})

    def __str__(self):
        return f"{self.staff} Block on {self.date}: {self.start_time}-{self.end_time} ({self.reason})"

