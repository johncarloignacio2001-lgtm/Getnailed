from django.core.management.base import BaseCommand

from apps.bookings.services import process_booking_reminders_and_grace_period


class Command(BaseCommand):
    help = "Process same-day & 4-5 hour customer reminders and 10-15 minute grace period no-show auto-releases."

    def handle(self, *args, **options):
        summary = process_booking_reminders_and_grace_period()
        self.stdout.write(
            self.style.SUCCESS(
                f"Booking alerts processed: day_of={summary['day_of_reminders_sent']}, "
                f"four_hour={summary['four_hour_reminders_sent']}, "
                f"grace_released={summary['grace_period_released']}"
            )
        )

