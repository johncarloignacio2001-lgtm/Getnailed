import os
import tempfile
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from apps.pos.models import Sale, SaleItem

from .models import ForecastResult, ForecastRun


MIN_OBSERVED_DAYS = 30
RANDOM_SEED = 42
CENT = Decimal("0.01")


def extract_completed_service_sales(start_date, end_date):
    rows = list(
        SaleItem.objects.filter(
            sale__status=Sale.Status.COMPLETED,
            sale__created_at__date__range=(start_date, end_date),
        ).values(
            "sale_id",
            "sale__created_at",
            "service_category",
            "line_total",
            "quantity",
        )
    )
    if not rows:
        return pd.DataFrame(
            columns=(
                "date",
                "service_category",
                "total_service_sales",
                "transaction_count",
                "service_quantity",
            )
        )
    frame = pd.DataFrame.from_records(rows)
    frame["date"] = frame["sale__created_at"].map(
        lambda value: timezone.localtime(value).date()
    )
    frame["service_category"] = (
        frame["service_category"].fillna("Uncategorized").astype(str).str.strip()
    )
    frame.loc[frame["service_category"] == "", "service_category"] = "Uncategorized"
    frame["line_total"] = pd.to_numeric(frame["line_total"], errors="coerce")
    frame["quantity"] = pd.to_numeric(frame["quantity"], errors="coerce")
    frame = frame.dropna(subset=("date", "line_total", "quantity"))
    frame = frame[(frame["line_total"] >= 0) & (frame["quantity"] > 0)]
    return (
        frame.groupby(["date", "service_category"], as_index=False)
        .agg(
            total_service_sales=("line_total", "sum"),
            transaction_count=("sale_id", "nunique"),
            service_quantity=("quantity", "sum"),
        )
        .sort_values(["service_category", "date"])
        .reset_index(drop=True)
    )


def clean_and_complete_series(extracted, start_date, end_date):
    if extracted.empty:
        return extracted.copy()
    categories = sorted(extracted["service_category"].unique())
    dates = pd.date_range(start_date, end_date, freq="D")
    index = pd.MultiIndex.from_product(
        (dates.date, categories), names=("date", "service_category")
    )
    completed = (
        extracted.set_index(["date", "service_category"])
        .reindex(index, fill_value=0)
        .reset_index()
    )
    completed["total_service_sales"] = completed["total_service_sales"].astype(float)
    completed["transaction_count"] = completed["transaction_count"].astype(float)
    completed["service_quantity"] = completed["service_quantity"].astype(float)
    return completed.sort_values(["service_category", "date"]).reset_index(drop=True)


def create_features(series, distinct_days):
    frame = series.copy()
    dates = pd.to_datetime(frame["date"])
    frame["date_ordinal"] = dates.map(pd.Timestamp.toordinal)
    frame["day_of_week"] = dates.dt.dayofweek
    frame["month"] = dates.dt.month
    frame["day_of_month"] = dates.dt.day
    frame["is_weekend"] = (dates.dt.dayofweek >= 5).astype(int)
    grouped = frame.groupby("service_category", sort=False)
    frame["total_service_sales_lag_1"] = grouped["total_service_sales"].shift(1)
    frame["transaction_count_lag_1"] = grouped["transaction_count"].shift(1)
    frame["total_service_sales_rolling_7"] = grouped[
        "total_service_sales"
    ].transform(lambda values: values.shift(1).rolling(7, min_periods=3).mean())
    frame["transaction_count_rolling_7"] = grouped["transaction_count"].transform(
        lambda values: values.shift(1).rolling(7, min_periods=3).mean()
    )
    numeric_features = [
        "date_ordinal",
        "day_of_week",
        "month",
        "day_of_month",
        "is_weekend",
        "total_service_sales_lag_1",
        "total_service_sales_rolling_7",
        "transaction_count_lag_1",
        "transaction_count_rolling_7",
    ]
    if distinct_days >= 14:
        frame["total_service_sales_lag_7"] = grouped["total_service_sales"].shift(7)
        numeric_features.append("total_service_sales_lag_7")
    if distinct_days >= 45:
        frame["total_service_sales_rolling_30"] = grouped[
            "total_service_sales"
        ].transform(lambda values: values.shift(1).rolling(30, min_periods=14).mean())
        numeric_features.append("total_service_sales_rolling_30")
    feature_columns = ["service_category", *numeric_features]
    return frame.dropna(subset=numeric_features).reset_index(drop=True), feature_columns


def _pipeline(feature_columns, parameters):
    numeric = [column for column in feature_columns if column != "service_category"]
    preprocessor = ColumnTransformer(
        [
            ("category", OneHotEncoder(handle_unknown="ignore"), ["service_category"]),
            ("numeric", "passthrough", numeric),
        ]
    )
    model = RandomForestRegressor(
        n_estimators=parameters["n_estimators"],
        max_depth=parameters["max_depth"],
        min_samples_leaf=parameters["min_samples_leaf"],
        random_state=RANDOM_SEED,
        n_jobs=1,
    )
    return Pipeline([("preprocessor", preprocessor), ("model", model)])


def _metric_values(actual, predicted):
    mae = float(mean_absolute_error(actual, predicted))
    rmse = float(np.sqrt(mean_squared_error(actual, predicted)))
    r2 = None
    if len(actual) >= 2 and np.unique(actual).size > 1:
        r2 = float(r2_score(actual, predicted))
    nonzero = np.asarray(actual) != 0
    mape = None
    if nonzero.any():
        mape = float(
            np.mean(
                np.abs(
                    (np.asarray(actual)[nonzero] - np.asarray(predicted)[nonzero])
                    / np.asarray(actual)[nonzero]
                )
            )
            * 100
        )
    return {"mae": mae, "rmse": rmse, "r2": r2, "mape": mape}


def _base_run(start_date, end_date, parameters, actor, distinct_days=0):
    return ForecastRun(
        training_start=start_date,
        training_end=end_date,
        parameters={**parameters, "random_state": RANDOM_SEED},
        distinct_days=distinct_days,
        trained_by=actor,
        sklearn_version=sklearn.__version__,
        pandas_version=pd.__version__,
    )


def train_forecast_model(
    *,
    start_date,
    end_date,
    actor,
    n_estimators=200,
    max_depth=None,
    min_samples_leaf=1,
):
    parameters = {
        "n_estimators": int(n_estimators),
        "max_depth": int(max_depth) if max_depth else None,
        "min_samples_leaf": int(min_samples_leaf),
    }
    extracted = extract_completed_service_sales(start_date, end_date)
    distinct_days = int(extracted["date"].nunique()) if not extracted.empty else 0
    run = _base_run(start_date, end_date, parameters, actor, distinct_days)
    if distinct_days < MIN_OBSERVED_DAYS:
        run.status = ForecastRun.Status.INSUFFICIENT_DATA
        run.sample_count = len(extracted)
        run.message = (
            f"At least {MIN_OBSERVED_DAYS} distinct days with completed, non-voided "
            f"sales are required; {distinct_days} were available. No model or accuracy "
            "metrics were generated."
        )
        run.completed_at = timezone.now()
        run.save()
        return run

    series = clean_and_complete_series(extracted, start_date, end_date)
    featured, feature_columns = create_features(series, distinct_days)
    dates = sorted(featured["date"].unique())
    split_index = max(1, int(len(dates) * 0.8))
    split_index = min(split_index, len(dates) - 1)
    training_dates = set(dates[:split_index])
    training = featured[featured["date"].isin(training_dates)]
    testing = featured[~featured["date"].isin(training_dates)]
    if training.empty or testing.empty:
        run.status = ForecastRun.Status.INSUFFICIENT_DATA
        run.sample_count = len(featured)
        run.message = (
            "The chronological holdout could not produce non-empty training and test "
            "sets. No model or accuracy metrics were generated."
        )
        run.completed_at = timezone.now()
        run.save()
        return run

    pipeline = _pipeline(feature_columns, parameters)
    target = "total_service_sales"
    pipeline.fit(training[feature_columns], training[target])
    predictions = pipeline.predict(testing[feature_columns])
    metrics = _metric_values(testing[target].to_numpy(), predictions)
    final_pipeline = clone(pipeline)
    final_pipeline.fit(featured[feature_columns], featured[target])

    run.status = ForecastRun.Status.TRAINED
    run.feature_columns = feature_columns
    run.service_categories = sorted(series["service_category"].unique().tolist())
    run.sample_count = len(featured)
    run.training_count = len(training)
    run.test_count = len(testing)
    run.mae = metrics["mae"]
    run.rmse = metrics["rmse"]
    run.r2 = metrics["r2"]
    run.mape = metrics["mape"]
    run.message = (
        "Metrics use a chronological 80/20 holdout. The persisted model was then "
        "refitted on all usable rows for future prediction."
    )
    run.completed_at = timezone.now()

    relative_path = Path("forecast-models") / f"{run.public_id}.joblib"
    target_path = Path(settings.MEDIA_ROOT) / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = {
        "pipeline": final_pipeline,
        "feature_columns": feature_columns,
        "categories": run.service_categories,
        "training_end": end_date.isoformat(),
        "history": series.to_dict("records"),
        "parameters": run.parameters,
        "target": target,
    }
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target_path.parent, suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        joblib.dump(artifact, temporary_path)
        os.replace(temporary_path, target_path)
        run.model_file_path = relative_path.as_posix()
        with transaction.atomic():
            run.save()
    except Exception:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()
        if target_path.exists():
            target_path.unlink()
        raise
    return run


def _artifact_path(run):
    root = Path(settings.MEDIA_ROOT).resolve()
    path = (root / run.model_file_path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValidationError("The persisted model artifact is unavailable.")
    return path


def _prediction_features(category_frame, forecast_date, feature_columns):
    sales = category_frame["total_service_sales"].astype(float).tolist()
    transactions = category_frame["transaction_count"].astype(float).tolist()
    timestamp = pd.Timestamp(forecast_date)
    row = {
        "service_category": category_frame["service_category"].iloc[0],
        "date_ordinal": timestamp.toordinal(),
        "day_of_week": timestamp.dayofweek,
        "month": timestamp.month,
        "day_of_month": timestamp.day,
        "is_weekend": int(timestamp.dayofweek >= 5),
        "total_service_sales_lag_1": sales[-1],
        "total_service_sales_rolling_7": float(np.mean(sales[-7:])),
        "transaction_count_lag_1": transactions[-1],
        "transaction_count_rolling_7": float(np.mean(transactions[-7:])),
    }
    if "total_service_sales_lag_7" in feature_columns:
        row["total_service_sales_lag_7"] = sales[-7]
    if "total_service_sales_rolling_30" in feature_columns:
        row["total_service_sales_rolling_30"] = float(np.mean(sales[-30:]))
    return row


def generate_forecasts(run, *, horizon_days):
    if not run.can_generate:
        raise ValidationError("Only successfully trained runs can generate forecasts.")
    horizon_days = int(horizon_days)
    if horizon_days < 1 or horizon_days > 365:
        raise ValidationError("Forecast horizon must be between 1 and 365 days.")
    artifact = joblib.load(_artifact_path(run))
    pipeline = artifact["pipeline"]
    feature_columns = artifact["feature_columns"]
    history = pd.DataFrame.from_records(artifact["history"])
    history["date"] = pd.to_datetime(history["date"]).dt.date
    records = []
    start_date = run.training_end + timedelta(days=1)

    for offset in range(horizon_days):
        forecast_date = start_date + timedelta(days=offset)
        feature_rows = []
        category_frames = {}
        for category in artifact["categories"]:
            category_frame = history[history["service_category"] == category].sort_values(
                "date"
            )
            category_frames[category] = category_frame
            feature_rows.append(
                _prediction_features(category_frame, forecast_date, feature_columns)
            )
        features = pd.DataFrame(feature_rows)[feature_columns]
        predicted = np.maximum(0, pipeline.predict(features))
        transformed = pipeline.named_steps["preprocessor"].transform(features)
        tree_predictions = np.array(
            [tree.predict(transformed) for tree in pipeline.named_steps["model"].estimators_]
        )
        lower = np.maximum(0, np.quantile(tree_predictions, 0.1, axis=0))
        upper = np.maximum(0, np.quantile(tree_predictions, 0.9, axis=0))
        for index, category in enumerate(artifact["categories"]):
            point = float(predicted[index])
            low = min(point, float(lower[index]))
            high = max(point, float(upper[index]))
            records.append(
                ForecastResult(
                    run=run,
                    forecast_date=forecast_date,
                    service_category=category,
                    predicted_sales=Decimal(str(point)).quantize(CENT, ROUND_HALF_UP),
                    lower_bound=Decimal(str(low)).quantize(CENT, ROUND_HALF_UP),
                    upper_bound=Decimal(str(high)).quantize(CENT, ROUND_HALF_UP),
                )
            )
            category_frame = category_frames[category]
            estimated_transactions = max(
                0.0, float(category_frame["transaction_count"].tail(7).mean())
            )
            history = pd.concat(
                [
                    history,
                    pd.DataFrame.from_records(
                        [
                            {
                                "date": forecast_date,
                                "service_category": category,
                                "total_service_sales": point,
                                "transaction_count": estimated_transactions,
                                "service_quantity": 0.0,
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
    with transaction.atomic():
        run.results.all().delete()
        ForecastResult.objects.bulk_create(records)
    return records
