from django.conf import settings
from django.db import models


class Notification(models.Model):
    class EventType(models.TextChoices):
        NEW = "NEW", "New appointment"
        APPROVED = "APPROVED", "Appointment approved"
        REJECTED = "REJECTED", "Appointment rejected"
        RESCHEDULED = "RESCHEDULED", "Appointment rescheduled"
        CANCELLED = "CANCELLED", "Appointment cancelled"
        REMINDER = "REMINDER", "Booking reminder"
        NO_SHOW_ALERT = "NO_SHOW_ALERT", "Late / No-show alert"
        MESSAGE = "MESSAGE", "Direct message"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    appointment = models.ForeignKey(
        "bookings.Appointment",
        on_delete=models.CASCADE,
        related_name="notifications",
        blank=True,
        null=True,
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    title = models.CharField(max_length=160)
    message = models.CharField(max_length=500)
    read_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        indexes = [models.Index(fields=("recipient", "read_at"), name="notification_unread_idx")]

    @property
    def is_read(self):
        return self.read_at is not None

    def __str__(self):
        return self.title


class SalonMessage(models.Model):
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="salon_messages",
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sent_salon_messages",
    )
    sender_name = models.CharField(max_length=160, blank=True)
    body = models.TextField()
    is_from_customer = models.BooleanField(default=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        direction = "Customer -> Salon" if self.is_from_customer else "Salon -> Customer"
        return f"[{direction}] {self.customer}: {self.body[:40]}"
