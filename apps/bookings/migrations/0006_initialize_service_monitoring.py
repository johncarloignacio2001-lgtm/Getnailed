from datetime import datetime, timedelta

from django.db import migrations
from django.utils import timezone


STATUS_MAP = {
    "UNVERIFIED": "PENDING",
    "PENDING": "PENDING",
    "APPROVED": "APPROVED",
    "RESCHEDULED": "APPROVED",
    "ONGOING": "ONGOING",
    "COMPLETED": "COMPLETED",
    "CANCELLED": "PENDING",
    "REJECTED": "PENDING",
    "NO_SHOW": "PENDING",
    "EXPIRED": "PENDING",
}


def initialize_service_monitoring(apps, schema_editor):
    Appointment = apps.get_model("bookings", "Appointment")
    AppointmentService = apps.get_model("bookings", "AppointmentService")

    for appointment in Appointment.objects.all().iterator():
        rows = list(
            AppointmentService.objects.filter(appointment=appointment).order_by(
                "position", "pk"
            )
        )
        cumulative_minutes = 0
        scheduled = timezone.make_aware(
            datetime.combine(appointment.appointment_date, appointment.start_time),
            timezone.get_current_timezone(),
        )
        mapped_status = STATUS_MAP.get(appointment.status, "PENDING")
        for row in rows:
            cumulative_minutes += row.duration_minutes
            row.assigned_staff_id = appointment.assigned_staff_id
            row.status = mapped_status
            if mapped_status in ("APPROVED", "ONGOING", "COMPLETED"):
                row.approved_at = appointment.verified_at or appointment.updated_at
            if mapped_status in ("ONGOING", "COMPLETED"):
                row.started_at = appointment.updated_at
                row.expected_finish_at = scheduled + timedelta(
                    minutes=cumulative_minutes
                )
            if mapped_status == "COMPLETED":
                row.completed_at = appointment.updated_at
        AppointmentService.objects.bulk_update(
            rows,
            (
                "assigned_staff",
                "status",
                "approved_at",
                "started_at",
                "expected_finish_at",
                "completed_at",
            ),
        )


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0005_appointmentservice_approved_at_and_more"),
    ]

    operations = [
        migrations.RunPython(initialize_service_monitoring, migrations.RunPython.noop),
    ]
