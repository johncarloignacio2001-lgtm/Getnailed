from django.db.models import Count, Sum
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import cashier_or_owner_required, owner_required
from apps.pos.models import Payment, Sale

from .exports import export_csv, export_pdf, export_xlsx
from .forms import DailySummaryForm, ReportDateRangeForm
from .services import build_report, completed_sales, sort_report_rows


REPORT_TYPES = {
    "daily": "Daily Sales",
    "weekly": "Weekly Sales",
    "monthly": "Monthly Sales",
    "annual": "Annual Sales",
    "service-sales": "Service Sales",
    "appointment-status": "Appointment Status",
    "staff-workload": "Staff Workload",
    "top-services": "Top Services (Most Booked)",
    "top-staff": "Top Performing Staff",
}


@owner_required
def index(request):
    return render(request, "reports/index.html", {"report_types": REPORT_TYPES})


def _report_and_form(request, report_type):
    form = ReportDateRangeForm(request.GET or None, report_type=report_type)
    if form.is_bound:
        if not form.is_valid():
            return None, form
        start_date = form.cleaned_data["start_date"]
        end_date = form.cleaned_data["end_date"]
    else:
        start_date = form.initial["start_date"]
        end_date = form.initial["end_date"]
    report = build_report(report_type, start_date, end_date)
    sort_column = request.GET.get("sort")
    direction = request.GET.get("direction", "asc")
    if sort_column and report:
        report.rows = sort_report_rows(report.rows, sort_column, direction)
    return report, form


def _render_report(request, report_type):
    report, form = _report_and_form(request, report_type)
    sort_column = request.GET.get("sort", "")
    direction = request.GET.get("direction", "asc")
    next_direction = "desc" if direction == "asc" else "asc"
    return render(
        request,
        "reports/report.html",
        {
            "report": report,
            "form": form,
            "report_type": report_type,
            "sort_column": sort_column,
            "direction": direction,
            "next_direction": next_direction,
        },
    )


@owner_required
def daily(request):
    return _render_report(request, "daily")


@owner_required
def weekly(request):
    return _render_report(request, "weekly")


@owner_required
def monthly(request):
    return _render_report(request, "monthly")


@owner_required
def annual(request):
    return _render_report(request, "annual")


@owner_required
def service_sales(request):
    return _render_report(request, "service-sales")


@owner_required
def appointment_status(request):
    return _render_report(request, "appointment-status")


@owner_required
def staff_workload(request):
    return _render_report(request, "staff-workload")


@owner_required
def top_services(request):
    return _render_report(request, "top-services")


@owner_required
def top_staff(request):
    return _render_report(request, "top-staff")


@owner_required
def export(request, report_type, export_format):
    if report_type not in REPORT_TYPES or export_format not in ("csv", "xlsx", "pdf"):
        return HttpResponseBadRequest("Unsupported report export.")
    report, form = _report_and_form(request, report_type)
    if report is None:
        return HttpResponseBadRequest("Choose a valid date range.")
    return {
        "csv": export_csv,
        "xlsx": export_xlsx,
        "pdf": export_pdf,
    }[export_format](report)


@cashier_or_owner_required
def daily_summary(request):
    form = DailySummaryForm(request.GET or None, actor=request.user)
    selected_date = timezone.localdate()
    selected_cashier = None
    if form.is_valid():
        selected_date = form.cleaned_data["date"]
        selected_cashier = form.cleaned_data.get("cashier")
    sales = Sale.objects.filter(created_at__date=selected_date)
    if request.user.is_cashier:
        sales = sales.filter(cashier=request.user)
    elif selected_cashier:
        sales = sales.filter(cashier=selected_cashier)
    completed = completed_sales(selected_date, selected_date).filter(pk__in=sales)
    totals = completed.aggregate(
        transactions=Count("pk"),
        subtotal=Sum("subtotal"),
        discounts=Sum("discount_amount"),
        net_sales=Sum("total"),
    )
    totals["subtotal"] = totals["subtotal"] or 0
    totals["discounts"] = totals["discounts"] or 0
    totals["net_sales"] = totals["net_sales"] or 0
    payment_breakdown = (
        Payment.objects.filter(sale__in=completed)
        .values("payment_method")
        .annotate(transactions=Count("pk"), total=Sum("sale__total"))
        .order_by("payment_method")
    )
    totals["voided"] = sales.filter(status=Sale.Status.VOIDED).count()
    return render(
        request,
        "reports/daily_summary.html",
        {
            "form": form,
            "selected_date": selected_date,
            "selected_cashier": selected_cashier,
            "totals": totals,
            "payment_breakdown": payment_breakdown,
            "sales": completed.select_related("cashier", "payment"),
        },
    )
