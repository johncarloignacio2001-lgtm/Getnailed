import csv
import logging

import pandas as pd
import sklearn
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.decorators import owner_required

from .forms import ForecastComparisonForm, ForecastGenerationForm, ForecastTrainingForm
from .models import ForecastRun
from .services import generate_forecasts, train_forecast_model


logger = logging.getLogger(__name__)


def _run(public_id):
    return get_object_or_404(ForecastRun, public_id=public_id)


@owner_required
def index(request):
    from datetime import datetime
    from decimal import Decimal

    runs = ForecastRun.objects.select_related("trained_by").prefetch_related("results").order_by("-created_at")
    latest_run = runs.filter(status=ForecastRun.Status.TRAINED).first()

    context = {
        "runs": runs,
        "latest_run": latest_run,
    }

    if latest_run:
        results = list(latest_run.results.all())
        total_sales = sum((r.predicted_sales for r in results), Decimal("0.00"))
        total_services = sum((r.predicted_service_quantity for r in results), Decimal("0.00"))

        cat_sales = {}
        cat_services = {}
        dates_set = set()
        for r in results:
            cat_sales[r.service_category] = cat_sales.get(r.service_category, Decimal("0.00")) + r.predicted_sales
            cat_services[r.service_category] = cat_services.get(r.service_category, Decimal("0.00")) + r.predicted_service_quantity
            dates_set.add(r.forecast_date.isoformat())

        sorted_dates = sorted(dates_set)
        sorted_categories = sorted(cat_sales.keys())

        top_cat_sales = max(cat_sales.items(), key=lambda x: x[1])[0] if cat_sales else "None"
        top_cat_services = max(cat_services.items(), key=lambda x: x[1])[0] if cat_services else "None"

        daily_sales = {}
        daily_services = {}
        for r in results:
            d = r.forecast_date.isoformat()
            daily_sales[d] = daily_sales.get(d, 0.0) + float(r.predicted_sales)
            daily_services[d] = daily_services.get(d, 0.0) + float(r.predicted_service_quantity)

        daily_breakdown = []
        for d in sorted_dates:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            daily_breakdown.append({
                "date": dt,
                "date_display": dt.strftime("%a, %b %d"),
                "sales": daily_sales.get(d, 0.0),
                "services": int(round(daily_services.get(d, 0.0))),
            })

        chart_payload = {
            "dates": sorted_dates,
            "daily_sales": [round(daily_sales.get(d, 0.0), 2) for d in sorted_dates],
            "daily_services": [round(daily_services.get(d, 0.0), 1) for d in sorted_dates],
            "categories": sorted_categories,
            "cat_sales": [round(float(cat_sales.get(c, 0.0)), 2) for c in sorted_categories],
            "cat_services": [round(float(cat_services.get(c, 0.0)), 1) for c in sorted_categories],
        }

        context.update({
            "results": results,
            "total_sales": total_sales,
            "total_services": total_services,
            "top_cat_sales": top_cat_sales,
            "top_cat_services": top_cat_services,
            "daily_breakdown": daily_breakdown,
            "chart_payload": chart_payload,
        })

    return render(request, "forecasting/index.html", context)


@owner_required
@require_http_methods(["POST"])
def quick_sync(request):
    """One-click automated training using actual salon POS sales data and automatic 14-day predictions."""
    from datetime import timedelta
    from apps.pos.models import Sale
    from .services import train_forecast_model, generate_forecasts

    today = timezone.localdate()
    earliest_sale = (
        Sale.objects.filter(status=Sale.Status.COMPLETED)
        .order_by("created_at")
        .first()
    )
    start_date = earliest_sale.created_at.date() if earliest_sale else today - timedelta(days=60)
    end_date = today

    try:
        run = train_forecast_model(
            start_date=start_date,
            end_date=end_date,
            actor=request.user,
            n_estimators=100,
            max_depth=10,
            min_samples_leaf=2,
        )
        if run.status == ForecastRun.Status.TRAINED:
            records = generate_forecasts(run, horizon_days=14)
            messages.success(request, f"AI model successfully trained on POS sales. Generated 14-day forecasts for {len(records)} category projections.")
        else:
            messages.warning(request, run.message or "At least 35 days of sales records are required to train the forecast model.")
    except Exception as exc:
        logger.exception("Quick sync forecast failed")
        messages.error(request, f"Forecast training could not complete: {exc}")

    return redirect("forecasting:index")


@owner_required
@require_http_methods(["GET", "POST"])
def train(request):
    form = ForecastTrainingForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            run = train_forecast_model(actor=request.user, **form.cleaned_data)
        except Exception:
            logger.exception("Forecast training failed")
            run = ForecastRun.objects.create(
                status=ForecastRun.Status.FAILED,
                training_start=form.cleaned_data["start_date"],
                training_end=form.cleaned_data["end_date"],
                parameters={
                    "n_estimators": form.cleaned_data["n_estimators"],
                    "max_depth": form.cleaned_data["max_depth"],
                    "min_samples_leaf": form.cleaned_data["min_samples_leaf"],
                    "random_state": 42,
                },
                sklearn_version=sklearn.__version__,
                pandas_version=pd.__version__,
                message="Training failed. No model or accuracy metrics were persisted.",
                trained_by=request.user,
                completed_at=timezone.now(),
            )
            messages.error(request, run.message)
        else:
            if run.status == ForecastRun.Status.TRAINED:
                messages.success(request, "Forecast model trained and evaluated.")
            else:
                messages.warning(request, run.message)
        return redirect("forecasting:detail", public_id=run.public_id)
    return render(request, "forecasting/train.html", {"form": form})


@owner_required
def detail(request, public_id):
    from decimal import Decimal
    run = _run(public_id)
    results = list(run.results.all())

    # Aggregate stats for Sales & Service Volume
    total_sales = sum((r.predicted_sales for r in results), Decimal("0.00"))
    total_services = sum((r.predicted_service_quantity for r in results), Decimal("0.00"))

    cat_sales = {}
    cat_services = {}
    dates_set = set()
    for r in results:
        cat_sales[r.service_category] = cat_sales.get(r.service_category, Decimal("0.00")) + r.predicted_sales
        cat_services[r.service_category] = cat_services.get(r.service_category, Decimal("0.00")) + r.predicted_service_quantity
        dates_set.add(r.forecast_date.isoformat())

    sorted_dates = sorted(dates_set)
    sorted_categories = sorted(cat_sales.keys())

    top_cat_sales = max(cat_sales.items(), key=lambda x: x[1])[0] if cat_sales else "None"
    top_cat_services = max(cat_services.items(), key=lambda x: x[1])[0] if cat_services else "None"

    # Daily aggregates for chart visualization
    daily_sales = {}
    daily_services = {}
    for r in results:
        d = r.forecast_date.isoformat()
        daily_sales[d] = daily_sales.get(d, 0.0) + float(r.predicted_sales)
        daily_services[d] = daily_services.get(d, 0.0) + float(r.predicted_service_quantity)

    chart_payload = {
        "dates": sorted_dates,
        "daily_sales": [round(daily_sales.get(d, 0.0), 2) for d in sorted_dates],
        "daily_services": [round(daily_services.get(d, 0.0), 1) for d in sorted_dates],
        "categories": sorted_categories,
        "cat_sales": [round(float(cat_sales.get(c, 0.0)), 2) for c in sorted_categories],
        "cat_services": [round(float(cat_services.get(c, 0.0)), 1) for c in sorted_categories],
    }

    return render(
        request,
        "forecasting/detail.html",
        {
            "run": run,
            "results": results,
            "total_sales": total_sales,
            "total_services": total_services,
            "top_cat_sales": top_cat_sales,
            "top_cat_services": top_cat_services,
            "chart_payload": chart_payload,
        },
    )


@owner_required
def evaluate(request, public_id):
    return render(request, "forecasting/evaluate.html", {"run": _run(public_id)})


@owner_required
@require_http_methods(["GET", "POST"])
def generate(request, public_id):
    run = _run(public_id)
    form = ForecastGenerationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            results = generate_forecasts(
                run, horizon_days=form.cleaned_data["horizon_days"]
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Generated {len(results)} forecast values.")
            return redirect("forecasting:detail", public_id=run.public_id)
    return render(request, "forecasting/generate.html", {"run": run, "form": form})


@owner_required
def compare(request):
    form = ForecastComparisonForm(request.GET or None)
    runs = []
    if form.is_valid():
        runs = list(form.cleaned_data["runs"])
    return render(request, "forecasting/compare.html", {"form": form, "runs": runs})


@owner_required
def export_screen(request, public_id):
    return render(request, "forecasting/export.html", {"run": _run(public_id)})


def _safe_csv(value):
    value = str(value)
    return f"'{value}" if value.startswith(("=", "+", "-", "@")) else value


@owner_required
def export_csv(request, public_id):
    run = _run(public_id)
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = (
        f'attachment; filename="forecast-{run.public_id}.csv"'
    )
    response.write("\ufeff")
    writer = csv.writer(response)
    writer.writerow(
        (
            "Run",
            "Forecast Date",
            "Service Category",
            "Predicted Sales",
            "Lower Bound",
            "Upper Bound",
            "Predicted Service Quantity",
            "Service Quantity Lower Bound",
            "Service Quantity Upper Bound",
        )
    )
    for result in run.results.all():
        writer.writerow(
            (
                run.public_id,
                result.forecast_date,
                _safe_csv(result.service_category),
                result.predicted_sales,
                result.lower_bound,
                result.upper_bound,
                result.predicted_service_quantity,
                result.service_quantity_lower_bound,
                result.service_quantity_upper_bound,
            )
        )
    return response
