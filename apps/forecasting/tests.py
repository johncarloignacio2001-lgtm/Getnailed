import tempfile
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.pos.models import Sale, SaleItem
from apps.services.models import Service, ServiceCategory

from .models import ForecastRun
from .services import (
    create_features,
    extract_completed_service_sales,
    generate_forecasts,
    train_forecast_model,
)


PASSWORD = "Correct-Horse-Battery-47!"


@override_settings(MFA_ENFORCE_OWNER=False, MFA_REQUIRE_INTERNAL_USERS=False)
class RandomForestForecastTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = cls.create_user("owner@example.com", User.Role.OWNER)
        cls.cashier = cls.create_user("cashier@example.com", User.Role.CASHIER)
        cls.staff = cls.create_user("staff@example.com", User.Role.STAFF)
        first_category = ServiceCategory.objects.create(name="Nails")
        second_category = ServiceCategory.objects.create(name="Spa")
        cls.first_service = Service.objects.create(
            category=first_category,
            name="Synthetic manicure",
            duration_minutes=45,
            price=Decimal("100.00"),
        )
        cls.second_service = Service.objects.create(
            category=second_category,
            name="Synthetic spa",
            duration_minutes=60,
            price=Decimal("50.00"),
        )
        cls.end_date = timezone.localdate() - timedelta(days=1)
        cls.start_date = cls.end_date - timedelta(days=54)
        for offset in range(55):
            sale_date = cls.start_date + timedelta(days=offset)
            weekend = 20 if sale_date.weekday() >= 5 else 0
            first_total = Decimal(100 + offset * 2 + weekend)
            second_total = Decimal(50 + offset + weekend // 2)
            sale = Sale.objects.create(
                receipt_number=f"GN-SYNTH-{offset:04d}",
                subtotal=first_total + second_total,
                total=first_total + second_total,
                cashier=cls.cashier,
                cashier_name_snapshot=str(cls.cashier),
            )
            created_at = timezone.make_aware(
                datetime.combine(sale_date, time(12, 0)),
                timezone.get_current_timezone(),
            )
            Sale.objects.filter(pk=sale.pk).update(created_at=created_at)
            SaleItem.objects.create(
                sale=sale,
                service=cls.first_service,
                service_name=cls.first_service.name,
                service_category="Nails",
                unit_price=first_total,
                quantity=1,
                line_total=first_total,
                position=0,
            )
            SaleItem.objects.create(
                sale=sale,
                service=cls.second_service,
                service_name=cls.second_service.name,
                service_category="Spa",
                unit_price=second_total,
                quantity=1,
                line_total=second_total,
                position=1,
            )
        voided = Sale.objects.create(
            receipt_number="GN-SYNTH-VOID",
            subtotal=Decimal("99999.00"),
            total=Decimal("99999.00"),
            status=Sale.Status.VOIDED,
            void_reason="Synthetic exclusion",
            voided_by=cls.owner,
            voided_at=timezone.now(),
            cashier=cls.cashier,
            cashier_name_snapshot=str(cls.cashier),
        )
        Sale.objects.filter(pk=voided.pk).update(
            created_at=timezone.make_aware(
                datetime.combine(cls.end_date, time(13, 0)),
                timezone.get_current_timezone(),
            )
        )
        SaleItem.objects.create(
            sale=voided,
            service=cls.first_service,
            service_name=cls.first_service.name,
            service_category="Nails",
            unit_price=Decimal("99999.00"),
            quantity=1,
            line_total=Decimal("99999.00"),
        )

    @classmethod
    def create_user(cls, email, role):
        return User.objects.create_user(
            email,
            PASSWORD,
            role=role,
            email_verified_at=timezone.now(),
            is_active=True,
            is_active_staff_member=True,
        )

    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.media_override.enable()

    def tearDown(self):
        self.media_override.disable()
        self.media_directory.cleanup()

    def train(self, **overrides):
        values = {
            "start_date": self.start_date,
            "end_date": self.end_date,
            "actor": self.owner,
            "n_estimators": 50,
            "max_depth": 8,
            "min_samples_leaf": 1,
        }
        values.update(overrides)
        return train_forecast_model(**values)

    def test_extraction_excludes_voids_and_feature_pipeline_has_required_fields(self):
        extracted = extract_completed_service_sales(self.start_date, self.end_date)
        self.assertEqual(extracted["date"].nunique(), 55)
        self.assertEqual(set(extracted["service_category"]), {"Nails", "Spa"})
        nails_last = extracted[
            (extracted["date"] == self.end_date)
            & (extracted["service_category"] == "Nails")
        ].iloc[0]
        self.assertLess(nails_last["total_service_sales"], 1000)
        featured, columns = create_features(extracted, 55)
        self.assertFalse(featured.empty)
        for required in (
            "service_category",
            "date_ordinal",
            "day_of_week",
            "month",
            "is_weekend",
            "total_service_sales_lag_1",
            "total_service_sales_rolling_7",
            "transaction_count_lag_1",
            "transaction_count_rolling_7",
            "total_service_sales_lag_7",
            "total_service_sales_rolling_30",
        ):
            self.assertIn(required, columns)

    def test_training_is_deterministic_and_persists_honest_metadata(self):
        first = self.train()
        second = self.train()
        self.assertEqual(first.status, ForecastRun.Status.TRAINED)
        self.assertEqual(first.mae, second.mae)
        self.assertEqual(first.rmse, second.rmse)
        self.assertEqual(first.r2, second.r2)
        self.assertEqual(first.mape, second.mape)
        self.assertGreater(first.training_count, 0)
        self.assertGreater(first.test_count, 0)
        self.assertEqual(first.distinct_days, 55)
        self.assertEqual(first.parameters["random_state"], 42)
        self.assertTrue((Path(self.media_directory.name) / first.model_file_path).is_file())
        self.assertIsNotNone(first.mae)
        self.assertIsNotNone(first.rmse)

    def test_forecast_generation_is_deterministic_nonnegative_and_replaces_horizon(self):
        run = self.train()
        first = generate_forecasts(run, horizon_days=5)
        values = [item.predicted_sales for item in first]
        self.assertEqual(len(first), 10)
        self.assertTrue(all(item.lower_bound <= item.predicted_sales <= item.upper_bound for item in first))
        self.assertTrue(all(item.predicted_sales >= 0 for item in first))

        second = generate_forecasts(run, horizon_days=5)
        self.assertEqual(values, [item.predicted_sales for item in second])
        generate_forecasts(run, horizon_days=3)
        self.assertEqual(run.results.count(), 6)
        self.assertEqual(
            run.results.first().forecast_date, self.end_date + timedelta(days=1)
        )

    def test_insufficient_data_creates_no_model_or_accuracy_claims(self):
        run = self.train(end_date=self.start_date + timedelta(days=9))
        self.assertEqual(run.status, ForecastRun.Status.INSUFFICIENT_DATA)
        self.assertEqual(run.distinct_days, 10)
        self.assertEqual(run.model_file_path, "")
        self.assertIsNone(run.mae)
        self.assertIsNone(run.rmse)
        self.assertIsNone(run.r2)
        self.assertIsNone(run.mape)
        self.assertIn("required", run.message)

    def test_owner_workflow_screens_generate_compare_and_export(self):
        run = self.train()
        other = self.train(n_estimators=60)
        self.client.force_login(self.owner)
        for url in (
            reverse("forecasting:index"),
            reverse("forecasting:train"),
            reverse("forecasting:detail", kwargs={"public_id": run.public_id}),
            reverse("forecasting:evaluate", kwargs={"public_id": run.public_id}),
            reverse("forecasting:generate", kwargs={"public_id": run.public_id}),
            reverse("forecasting:export", kwargs={"public_id": run.public_id}),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(
            reverse("forecasting:generate", kwargs={"public_id": run.public_id}),
            {"horizon_days": 2},
        )
        self.assertEqual(response.status_code, 302)
        compare = self.client.get(
            reverse("forecasting:compare"), {"runs": [run.pk, other.pk]}
        )
        self.assertContains(compare, str(run.public_id))
        export = self.client.get(
            reverse("forecasting:export_csv", kwargs={"public_id": run.public_id})
        )
        self.assertTrue(export["Content-Type"].startswith("text/csv"))
        self.assertIn(b"Forecast Date", export.content)
        self.assertIn(b"Nails", export.content)

    def test_all_forecasting_routes_are_owner_only(self):
        run = self.train()
        routes = (
            reverse("forecasting:index"),
            reverse("forecasting:train"),
            reverse("forecasting:compare"),
            reverse("forecasting:detail", kwargs={"public_id": run.public_id}),
            reverse("forecasting:evaluate", kwargs={"public_id": run.public_id}),
            reverse("forecasting:generate", kwargs={"public_id": run.public_id}),
            reverse("forecasting:export", kwargs={"public_id": run.public_id}),
            reverse("forecasting:export_csv", kwargs={"public_id": run.public_id}),
        )
        for user in (self.cashier, self.staff):
            self.client.force_login(user)
            for route in routes:
                with self.subTest(role=user.role, route=route):
                    self.assertEqual(self.client.get(route).status_code, 403)
