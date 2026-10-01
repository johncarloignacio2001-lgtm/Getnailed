import uuid

from django.conf import settings
from django.db import models


class ForecastRun(models.Model):
    class Status(models.TextChoices):
        TRAINED = "TRAINED", "Trained"
        INSUFFICIENT_DATA = "INSUFFICIENT_DATA", "Insufficient data"
        FAILED = "FAILED", "Failed"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices)
    model_type = models.CharField(max_length=100, default="RandomForestRegressor")
    training_start = models.DateField()
    training_end = models.DateField()
    parameters = models.JSONField(default=dict)
    feature_columns = models.JSONField(default=list)
    service_categories = models.JSONField(default=list)
    sample_count = models.PositiveIntegerField(default=0)
    training_count = models.PositiveIntegerField(default=0)
    test_count = models.PositiveIntegerField(default=0)
    distinct_days = models.PositiveIntegerField(default=0)
    mae = models.FloatField(blank=True, null=True)
    rmse = models.FloatField(blank=True, null=True)
    r2 = models.FloatField(blank=True, null=True)
    mape = models.FloatField(blank=True, null=True)
    model_file_path = models.CharField(max_length=500, blank=True)
    sklearn_version = models.CharField(max_length=30, blank=True)
    pandas_version = models.CharField(max_length=30, blank=True)
    message = models.TextField(blank=True)
    trained_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="forecast_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ("-created_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=models.Q(training_end__gte=models.F("training_start")),
                name="forecast_training_range_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=("TRAINED", "INSUFFICIENT_DATA", "FAILED")
                ),
                name="forecast_run_status_valid",
            ),
        ]

    @property
    def can_generate(self):
        return self.status == self.Status.TRAINED and bool(self.model_file_path)

    def __str__(self):
        return f"{self.model_type} {self.public_id}"


class ForecastResult(models.Model):
    run = models.ForeignKey(
        ForecastRun,
        on_delete=models.CASCADE,
        related_name="results",
    )
    forecast_date = models.DateField()
    service_category = models.CharField(max_length=100)
    predicted_sales = models.DecimalField(max_digits=12, decimal_places=2)
    lower_bound = models.DecimalField(max_digits=12, decimal_places=2)
    upper_bound = models.DecimalField(max_digits=12, decimal_places=2)
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("forecast_date", "service_category")
        constraints = [
            models.UniqueConstraint(
                fields=("run", "forecast_date", "service_category"),
                name="forecast_result_run_date_category_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(predicted_sales__gte=0),
                name="forecast_predicted_sales_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(lower_bound__gte=0),
                name="forecast_lower_bound_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(upper_bound__gte=models.F("lower_bound")),
                name="forecast_bounds_valid",
            ),
        ]

    def __str__(self):
        return f"{self.forecast_date} - {self.service_category}"
