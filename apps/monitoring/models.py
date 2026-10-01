from django.conf import settings
from django.db import models

from apps.bookings.models import AppointmentService


class ServiceStatusHistory(models.Model):
    appointment_service = models.ForeignKey(
        AppointmentService,
        on_delete=models.CASCADE,
        related_name="status_history",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="service_status_changes",
    )
    old_status = models.CharField(max_length=12, choices=AppointmentService.Status.choices)
    new_status = models.CharField(max_length=12, choices=AppointmentService.Status.choices)
    note = models.CharField(max_length=500, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("timestamp", "pk")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(old_status=models.F("new_status")),
                name="service_status_transition_changes_state",
            )
        ]

    def __str__(self):
        return f"{self.appointment_service}: {self.old_status} -> {self.new_status}"
