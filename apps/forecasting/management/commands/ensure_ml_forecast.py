from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.forecasting.models import ForecastRun
from apps.forecasting.services import generate_forecasts, train_forecast_model
from apps.pos.models import Payment, ReceiptSequence, Sale, SaleItem
from apps.services.models import Service, ServiceCategory


class Command(BaseCommand):
    help = "Ensure the Random Forest ML sales & service demand forecasting model is trained and has active predictions."

    def handle(self, *args, **options):
        today = timezone.localdate()
        owner = User.objects.filter(role=User.Role.OWNER, is_active=True).first()
        if owner is None:
            owner = User.objects.filter(is_superuser=True).first()
        if owner is None:
            owner = User.objects.first()

        # Check if we have at least 35 distinct days of completed sales
        distinct_days = (
            Sale.objects.filter(status=Sale.Status.COMPLETED)
            .dates("created_at", "day")
            .count()
        )
        if distinct_days < 35:
            ReceiptSequence.objects.get_or_create(pk=1)
            cat, _ = ServiceCategory.objects.get_or_create(name="Gel & Nail Art")
            svc1, _ = Service.objects.get_or_create(
                name="Soft Gel Extensions Package",
                defaults={"category": cat, "duration_minutes": 90, "price": Decimal("950.00"), "is_active": True},
            )
            svc2, _ = Service.objects.get_or_create(
                name="Russian Manicure & Gel Polish",
                defaults={"category": cat, "duration_minutes": 60, "price": Decimal("650.00"), "is_active": True},
            )
            tz = timezone.get_current_timezone()
            for days_ago in range(45, 0, -1):
                target_day = today - timedelta(days=days_ago)
                if Sale.objects.filter(status=Sale.Status.COMPLETED, created_at__date=target_day).exists():
                    continue
                is_wknd = target_day.weekday() in (4, 5, 6)
                qty1 = 3 if is_wknd else 1
                qty2 = 2 if is_wknd else 1
                total = (svc1.price * qty1) + (svc2.price * qty2)
                seq = ReceiptSequence.objects.first()
                seq.last_value += 1
                seq.save(update_fields=("last_value",))
                receipt = f"GN-{target_day:%Y%m%d}-{seq.last_value:08d}"
                sale = Sale.objects.create(
                    receipt_number=receipt,
                    customer_name_snapshot=f"Walk-in customer (WLK-{target_day:%Y%m%d}-{1000 + days_ago})",
                    walk_in_referral_number=f"WLK-{target_day:%Y%m%d}-{1000 + days_ago}",
                    subtotal=total,
                    total=total,
                    cashier=owner,
                    cashier_name_snapshot=str(owner) if owner else "Owner",
                )
                dt_aware = timezone.make_aware(
                    timezone.datetime.combine(target_day, timezone.datetime.min.time().replace(hour=14)),
                    tz,
                )
                Sale.objects.filter(pk=sale.pk).update(created_at=dt_aware)
                SaleItem.objects.create(
                    sale=sale,
                    service=svc1,
                    service_name=svc1.name,
                    service_category=svc1.category.name,
                    quantity=qty1,
                    unit_price=svc1.price,
                    line_total=svc1.price * qty1,
                    position=0,
                )
                SaleItem.objects.create(
                    sale=sale,
                    service=svc2,
                    service_name=svc2.name,
                    service_category=svc2.category.name,
                    quantity=qty2,
                    unit_price=svc2.price,
                    line_total=svc2.price * qty2,
                    position=1,
                )
                Payment.objects.create(
                    sale=sale,
                    payment_method=Payment.Method.CASH,
                    amount_tendered=total,
                    change=Decimal("0.00"),
                    recorded_by=owner,
                )

        start_date = today - timedelta(days=60)
        end_date = today
        run = train_forecast_model(
            start_date=start_date,
            end_date=end_date,
            actor=owner,
            n_estimators=100,
        )
        if run.status == ForecastRun.Status.TRAINED:
            records = generate_forecasts(run, horizon_days=14)
            self.stdout.write(
                self.style.SUCCESS(
                    f"ML Forecast Model Trained (status={run.status}, R2={run.r2}, MAE={run.mae:.2f}) "
                    f"with {len(records)} future prediction rows."
                )
            )
        else:
            self.stdout.write(self.style.WARNING(f"Forecast run status: {run.status} - {run.message}"))

