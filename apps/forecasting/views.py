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
    runs = ForecastRun.objects.select_related("trained_by").prefetch_related("results")
    return render(request, "forecasting/index.html", {"runs": runs})


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
    run = _run(public_id)
    results = run.results.all()
    return render(
        request,
        "forecasting/detail.html",
        {"run": run, "results": results},
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
            )
        )
    return response
