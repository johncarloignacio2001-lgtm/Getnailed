# Stage 6 Random Forest Forecasting Report

Date: 2026-07-23

## Implemented Scope

- KDD-style forecasting pipeline covering extraction, cleaning, feature creation, training, evaluation, prediction, and persistence.
- `RandomForestRegressor` with deterministic random seed and configurable tree count, maximum depth, and minimum leaf size.
- Extraction uses only completed, non-voided `SaleItem` records.
- Immutable service-category snapshots added to future POS items, with a migration that captures the best available current category for historical items.
- Daily service-category aggregation with gross service sales, transaction count, and service quantity.
- Missing category/date combinations completed with zero observations after categories are discovered from valid sales.
- Calendar features: date ordinal, day of week, month, day of month, and weekend flag.
- Historical sales features: one-day lag, seven-day lag when supported, seven-day rolling average, and thirty-day rolling average when supported.
- Historical transaction features: one-day lag and seven-day rolling average.
- Service category one-hot encoding with unknown-category handling.
- Chronological 80/20 train/test split rather than random shuffling.
- MAE and RMSE for every valid holdout.
- R2 only when the holdout has enough observations and varying actual targets.
- MAPE only over nonzero actual targets; omitted when no valid denominator exists.
- Final persisted model refitted on all usable historical rows only after holdout evaluation.
- Recursive future forecasts per service category with deterministic point predictions.
- 10th and 90th percentile bounds derived from individual forest trees and constrained around the point estimate.
- Nonnegative database-constrained persisted forecast values and valid bound ordering.
- Atomic replacement of a run's generated horizon.
- Internal joblib model artifacts stored under `MEDIA_ROOT/forecast-models/` with UUID filenames.
- Artifact paths validated to remain inside `MEDIA_ROOT` before loading.
- Temporary/final artifact cleanup if database persistence fails.
- Explicit TRAINED, INSUFFICIENT_DATA, and FAILED run states.
- Insufficient datasets persist the observed-day count and explanation but no artifact or accuracy metrics.
- OWNER-only train, inspect, evaluate, generate, compare, export, and read-only admin workflows.
- CSV export of persisted forecasts with spreadsheet-formula injection protection.

## Models

### `ForecastRun`

- Public UUID and status.
- Model type and library versions.
- Training date range.
- Random Forest parameters and random seed.
- Feature names and service categories.
- Observed days, usable samples, training rows, and test rows.
- Nullable MAE, RMSE, R2, and MAPE.
- Relative model artifact path.
- Honest status/explanation message, trainer, and timestamps.

### `ForecastResult`

- Forecast run.
- Forecast date and service category.
- Point prediction, lower bound, and upper bound.
- Generation timestamp.
- Unique run/date/category constraint.

## Data Sufficiency

Training requires at least 30 distinct dates containing completed, non-voided sales. A broad calendar range containing only a few actual sales dates does not satisfy this requirement.

If the requirement is not met:

- The run is saved as `INSUFFICIENT_DATA`.
- No model artifact is written.
- MAE, RMSE, R2, and MAPE remain null.
- The UI explains the exact required and observed day counts.

## Files And Areas

- Forecast models: `apps/forecasting/models.py`
- KDD/training/prediction pipeline: `apps/forecasting/services.py`
- Owner forms: `apps/forecasting/forms.py`
- Owner workflows and CSV export: `apps/forecasting/views.py`
- Forecast routes: `apps/forecasting/urls.py`
- Read-only admin: `apps/forecasting/admin.py`
- Screens: `templates/forecasting/`
- Responsive styles: `static/css/app.css`
- Deterministic synthetic tests: `apps/forecasting/tests.py`
- POS category snapshot: `apps/pos/models.py`, `apps/pos/services.py`

## Migrations

- `forecasting.0001_initial`
- `pos.0003_saleitem_service_category`

Both migrations are applied to the working database.

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 166 tests passed in 58.827 seconds |
| Forecasting tests | 6 passed in 2.062 seconds |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

## Tested Behaviors

- Voided high-value outliers excluded from extraction.
- Required calendar, category, sales lag/rolling, and transaction lag/rolling features created.
- Two runs with identical data and parameters produce identical holdout metrics.
- Persisted model metadata, versions, random seed, row counts, metrics, and artifact path.
- Recursive predictions deterministic across repeated generation.
- Forecast values and percentile bounds remain nonnegative and correctly ordered.
- Regenerating a shorter horizon removes stale longer-horizon results.
- Insufficient history creates no model or accuracy claims.
- OWNER train, detail, evaluate, generate, compare, export, and index screens.
- CSV forecast export.
- All forecasting routes denied to CASHIER and STAFF.

## Important Interpretation

- The target is daily gross service-item sales by category before sale-level discount allocation.
- Transaction count and total service sales enter the model through lagged and rolling historical features, not same-day future values. This avoids using unavailable future data as if it were known.
- Metrics describe a chronological historical holdout only. They are not presented as guaranteed future accuracy.
- Percentile bounds reflect dispersion among trees in the fitted forest; they are not calibrated statistical confidence intervals.

## Deferred Work

- Promotions, holidays, weather, staffing levels, capacity, prices, and external economic features are not modeled.
- Sale-level discounts are not allocated to service categories, so the target is gross service-item sales.
- Hyperparameter search, cross-validation, backtesting windows, drift monitoring, automatic retraining, and champion/challenger promotion are not included.
- Training and forecast generation run synchronously. Larger production datasets should use background jobs with run cancellation and resource limits.
- Model artifacts require a durable shared filesystem or object-storage integration in multi-instance deployments.
- Joblib artifacts can execute Python during loading. This implementation loads only internally generated UUID-named files whose resolved paths remain under configured media storage; external model uploads are not accepted.
- Forecasts are not financial advice, staffing commitments, or guaranteed revenue.

This report covers Stage 6 Random Forest forecasting only. It does not claim causal inference, calibrated uncertainty, automated decision-making, or guaranteed predictive performance.
