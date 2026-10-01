from django.db import migrations


STATUS_MAP = {
    "UNVERIFIED": "UNVERIFIED",
    "CONFIRMED": "PENDING",
    "CANCELLED": "CANCELLED",
    "EXPIRED": "EXPIRED",
}


def split_name(value):
    parts = value.strip().split(maxsplit=1)
    if not parts:
        return "Customer", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts


def copy_legacy_bookings(apps, schema_editor):
    Booking = apps.get_model("bookings", "Booking")
    Appointment = apps.get_model("bookings", "Appointment")
    AppointmentService = apps.get_model("bookings", "AppointmentService")
    Customer = apps.get_model("customers", "Customer")

    for booking in Booking.objects.all().iterator():
        first_name, last_name = split_name(booking.customer_name)
        email = booking.email.strip().lower()
        if email:
            customer, created = Customer.objects.get_or_create(
                email=email,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "phone": booking.phone_number,
                },
            )
            if not created and not customer.phone and booking.phone_number:
                customer.phone = booking.phone_number
                customer.save(update_fields=("phone", "updated_at"))
        else:
            customer = Customer.objects.create(
                first_name=first_name,
                last_name=last_name,
                phone=booking.phone_number,
            )

        appointment = Appointment.objects.create(
            booking_reference=booking.reference,
            customer=customer,
            customer_name_snapshot=booking.customer_name,
            customer_email_snapshot=email,
            customer_phone_snapshot=booking.phone_number,
            appointment_date=booking.scheduled_for.date(),
            start_time=booking.scheduled_for.time().replace(tzinfo=None),
            end_time=None,
            booking_source="PUBLIC",
            status=STATUS_MAP.get(booking.status, "PENDING"),
            expires_at=booking.expires_at,
            verification_code_digest=booking.verification_code_digest,
            verification_code_expires_at=booking.verification_code_expires_at,
            verification_failed_attempts=booking.verification_failed_attempts,
            verification_sent_at=booking.verification_sent_at,
            verification_resend_count=booking.verification_resend_count,
            public_access_token_digest=booking.public_access_token_digest,
            public_access_expires_at=booking.public_access_expires_at,
            verified_at=booking.verified_at,
            cancelled_at=booking.cancelled_at,
            requires_schedule_review=True,
            legacy_booking_id=booking.pk,
        )
        Appointment.objects.filter(pk=appointment.pk).update(
            created_at=booking.created_at,
            updated_at=booking.updated_at,
        )
        AppointmentService.objects.create(
            appointment=appointment,
            service_name=booking.service_name,
            duration_minutes=60,
            price="0.00",
            position=0,
        )


def remove_copied_bookings(apps, schema_editor):
    Appointment = apps.get_model("bookings", "Appointment")
    Appointment.objects.filter(legacy_booking_id__isnull=False).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("bookings", "0003_appointment_appointmentservice_and_more"),
    ]

    operations = [
        migrations.RunPython(copy_legacy_bookings, remove_copied_bookings),
    ]
