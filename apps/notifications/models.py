from django.conf import settings
from django.db import models


class Notification(models.Model):
    class EventType(models.TextChoices):
        NEW = "NEW", "New appointment"
        APPROVED = "APPROVED", "Appointment approved"
        REJECTED = "REJECTED", "Appointment rejected"
        RESCHEDULED = "RESCHEDULED", "Appointment rescheduled"
        CANCELLED = "CANCELLED", "Appointment cancelled"

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    appointment = models.ForeignKey(
        "bookings.Appointment",
        on_delete=models.CASCADE,
        related_name="notifications",
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
