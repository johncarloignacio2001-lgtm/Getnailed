from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDay, TruncMonth, TruncWeek, TruncYear
from django.utils import timezone

from apps.accounts.models import User
from apps.bookings.models import Appointment, AppointmentService
from apps.customers.models import Customer
from apps.notifications.models import Notification
from apps.pos.models import Sale, SaleItem


ZERO = Decimal("0.00")
VISIBLE_APPOINTMENT_STATUSES = tuple(
    value
    for value, _ in Appointment.Status.choices
    if value not in (Appointment.Status.UNVERIFIED, Appointment.Status.EXPIRED)
)
WORKLOAD_APPOINTMENT_STATUSES = (
    Appointment.Status.PENDING,
    Appointment.Status.APPROVED,
    Appointment.Status.RESCHEDULED,
    Appointment.Status.ONGOING,
    Appointment.Status.COMPLETED,
)


@dataclass
class ReportResult:
    key: str
    title: str
    description: str
    columns: tuple
    rows: list
    totals: dict
    start_date: object
    end_date: object


def completed_sales(start_date=None, end_date=None):
    sales = Sale.objects.filter(status=Sale.Status.COMPLETED)
    if start_date is not None:
        sales = sales.filter(created_at__date__gte=start_date)
    if end_date is not None:
        sales = sales.filter(created_at__date__lte=end_date)
    return sales


def _financial_totals(sales):
    values = sales.aggregate(
        transactions=Count("pk"),
        gross=Sum("subtotal"),
        discounts=Sum("discount_amount"),
        net=Sum("total"),
    )
    for key in ("gross", "discounts", "net"):
        values[key] = values[key] or ZERO
    return values


def owner_dashboard_data():
    today = timezone.localdate()
    today_sales = completed_sales(today, today)
    trend_start = today - timedelta(days=6)
    trend_values = {
        row["day"]: row["total"]
        for row in completed_sales(trend_start, today)
        .annotate(day=TruncDay("created_at"))
        .values("day")
        .annotate(total=Sum("total"))
    }
    sales_trend = []
    for offset in range(7):
        day = trend_start + timedelta(days=offset)
        aware_key = next(
            (key for key in trend_values if timezone.localtime(key).date() == day), None
        )
        sales_trend.append(
            {"date": day, "total": trend_values.get(aware_key, ZERO) or ZERO}
        )
    sales_trend_max = max((item["total"] for item in sales_trend), default=ZERO)
    for item in sales_trend:
        item["percent"] = (
            int(item["total"] / sales_trend_max * 100) if sales_trend_max else 0
        )
    top_services = list(
        SaleItem.objects.filter(sale__in=completed_sales())
        .values("service_name")
        .annotate(quantity=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-quantity", "-revenue", "service_name")[:5]
    )
    top_staff = list(
        User.objects.filter(role=User.Role.STAFF)
        .annotate(
            completed_services=Count(
                "assigned_service_work",
                filter=Q(
                    assigned_service_work__status=AppointmentService.Status.COMPLETED
                ),
            )
        )
        .filter(completed_services__gt=0)
        .order_by("-completed_services", "first_name", "last_name", "email")[:5]
    )
    visible_customers = Customer.objects.filter(
        Q(appointments__isnull=True)
        | Q(appointments__status__in=VISIBLE_APPOINTMENT_STATUSES)
    ).distinct()
    return {
        "today": today,
        "today_sales": _financial_totals(today_sales),
        "customer_count": visible_customers.count(),
        "appointment_count": Appointment.objects.filter(
            status__in=VISIBLE_APPOINTMENT_STATUSES
        ).count(),
        "ongoing_services": AppointmentService.objects.filter(
            status=AppointmentService.Status.ONGOING
        ).count(),
        "top_services": top_services,
        "top_staff": top_staff,
        "recent_transactions": completed_sales().select_related("cashier", "payment")[:8],
        "sales_trend": sales_trend,
        "sales_trend_max": sales_trend_max,
    }


def cashier_dashboard_data(user):
    today = timezone.localdate()
    sales = completed_sales(today, today).filter(cashier=user)
    appointments = Appointment.objects.filter(
        appointment_date=today, status__in=VISIBLE_APPOINTMENT_STATUSES
    ).select_related("customer", "assigned_staff")
    return {
        "today": today,
        "pos_totals": _financial_totals(sales),
        "bookings_count": appointments.count(),
        "pending_bookings": appointments.filter(status=Appointment.Status.PENDING).count(),
        "appointments": appointments[:8],
        "recent_transactions": sales.select_related("payment")[:8],
    }


def staff_dashboard_data(user):
    today = timezone.localdate()
    work = (
        AppointmentService.objects.filter(
            assigned_staff=user,
            appointment__appointment_date=today,
        )
        .exclude(
            appointment__status__in=(
                Appointment.Status.UNVERIFIED,
                Appointment.Status.CANCELLED,
                Appointment.Status.REJECTED,
                Appointment.Status.NO_SHOW,
                Appointment.Status.EXPIRED,
            )
        )
        .select_related("appointment", "appointment__customer")
        .order_by("appointment__start_time", "position")
    )
    notifications = Notification.objects.filter(recipient=user).select_related(
        "appointment"
    )[:8]
    return {
        "today": today,
        "assigned_work": work,
        "assigned_count": work.count(),
        "ongoing_count": work.filter(status=AppointmentService.Status.ONGOING).count(),
        "completed_count": work.filter(status=AppointmentService.Status.COMPLETED).count(),
        "unread_notifications": Notification.objects.filter(
            recipient=user, read_at__isnull=True
        ).count(),
        "notifications": notifications,
    }


def _period_sales_report(report_type, start_date, end_date):
    truncation = {
        "daily": TruncDay,
        "weekly": TruncWeek,
        "monthly": TruncMonth,
        "annual": TruncYear,
    }[report_type]
    sales = completed_sales(start_date, end_date)
    values = (
        sales.annotate(period=truncation("created_at"))
        .values("period")
        .annotate(
            transactions=Count("pk"),
            gross=Sum("subtotal"),
            discounts=Sum("discount_amount"),
            net=Sum("total"),
        )
        .order_by("period")
    )
    rows = [
        {
            "Period": timezone.localtime(row["period"]).date(),
            "Transactions": row["transactions"],
            "Gross Sales": row["gross"] or ZERO,
            "Discounts": row["discounts"] or ZERO,
            "Net Sales": row["net"] or ZERO,
        }
        for row in values
    ]
    labels = {
        "daily": "Daily Sales",
        "weekly": "Weekly Sales",
        "monthly": "Monthly Sales",
        "annual": "Annual Sales",
    }
    return ReportResult(
        key=report_type,
        title=labels[report_type],
        description="Completed, non-voided sales grouped by period.",
        columns=("Period", "Transactions", "Gross Sales", "Discounts", "Net Sales"),
        rows=rows,
        totals=_financial_totals(sales),
        start_date=start_date,
        end_date=end_date,
    )


def _service_sales_report(start_date, end_date):
    items = SaleItem.objects.filter(sale__in=completed_sales(start_date, end_date))
    values = (
        items.values("service_name")
        .annotate(
            quantity=Sum("quantity"),
            transactions=Count("sale", distinct=True),
            gross=Sum("line_total"),
        )
        .order_by("-gross", "service_name")
    )
    rows = [
        {
            "Service": row["service_name"],
            "Quantity": row["quantity"],
            "Transactions": row["transactions"],
            "Gross Service Sales": row["gross"] or ZERO,
        }
        for row in values
    ]
    totals = {
        "transactions": completed_sales(start_date, end_date).count(),
        "gross": sum((row["Gross Service Sales"] for row in rows), ZERO),
        "discounts": ZERO,
        "net": sum((row["Gross Service Sales"] for row in rows), ZERO),
    }
    return ReportResult(
        key="service-sales",
        title="Service Sales",
        description="Gross service-item sales from completed, non-voided transactions.",
        columns=("Service", "Quantity", "Transactions", "Gross Service Sales"),
        rows=rows,
        totals=totals,
        start_date=start_date,
        end_date=end_date,
    )


def _appointment_status_report(start_date, end_date):
    values = (
        Appointment.objects.filter(
            appointment_date__range=(start_date, end_date),
            status__in=VISIBLE_APPOINTMENT_STATUSES,
        )
        .values("status")
        .annotate(count=Count("pk"))
        .order_by("status")
    )
    labels = dict(Appointment.Status.choices)
    rows = [
        {"Status": labels[row["status"]], "Appointments": row["count"]}
        for row in values
    ]
    return ReportResult(
        key="appointment-status",
        title="Appointment Status",
        description="Verified appointments grouped by current status.",
        columns=("Status", "Appointments"),
        rows=rows,
        totals={"appointments": sum(row["Appointments"] for row in rows)},
        start_date=start_date,
        end_date=end_date,
    )


def _staff_workload_report(start_date, end_date):
    staff = (
        User.objects.filter(role=User.Role.STAFF)
        .annotate(
            assigned=Count(
                "assigned_service_work",
                filter=Q(
                    assigned_service_work__appointment__appointment_date__range=(
                        start_date,
                        end_date,
                    ),
                    assigned_service_work__appointment__status__in=WORKLOAD_APPOINTMENT_STATUSES,
                ),
            ),
            completed=Count(
                "assigned_service_work",
                filter=Q(
                    assigned_service_work__appointment__appointment_date__range=(
                        start_date,
                        end_date,
                    ),
                    assigned_service_work__appointment__status__in=WORKLOAD_APPOINTMENT_STATUSES,
                    assigned_service_work__status=AppointmentService.Status.COMPLETED,
                ),
            ),
            ongoing=Count(
                "assigned_service_work",
                filter=Q(
                    assigned_service_work__appointment__appointment_date__range=(
                        start_date,
                        end_date,
                    ),
                    assigned_service_work__appointment__status__in=WORKLOAD_APPOINTMENT_STATUSES,
                    assigned_service_work__status=AppointmentService.Status.ONGOING,
                ),
            ),
            minutes=Sum(
                "assigned_service_work__duration_minutes",
                filter=Q(
                    assigned_service_work__appointment__appointment_date__range=(
                        start_date,
                        end_date,
                    ),
                    assigned_service_work__appointment__status__in=WORKLOAD_APPOINTMENT_STATUSES,
                ),
            ),
        )
        .filter(assigned__gt=0)
        .order_by("-completed", "first_name", "last_name", "email")
    )
    rows = [
        {
            "Staff": str(user),
            "Assigned Services": user.assigned,
            "Completed Services": user.completed,
            "Ongoing Services": user.ongoing,
            "Scheduled Minutes": user.minutes or 0,
        }
        for user in staff
    ]
    return ReportResult(
        key="staff-workload",
        title="Staff Workload",
        description="Assigned operational service workload by staff member.",
        columns=(
            "Staff",
            "Assigned Services",
            "Completed Services",
            "Ongoing Services",
            "Scheduled Minutes",
        ),
        rows=rows,
        totals={"assigned": sum(row["Assigned Services"] for row in rows)},
        start_date=start_date,
        end_date=end_date,
    )


def build_report(report_type, start_date, end_date):
    if report_type in ("daily", "weekly", "monthly", "annual"):
        return _period_sales_report(report_type, start_date, end_date)
    if report_type == "service-sales":
        return _service_sales_report(start_date, end_date)
    if report_type == "appointment-status":
        return _appointment_status_report(start_date, end_date)
    if report_type == "staff-workload":
        return _staff_workload_report(start_date, end_date)
    raise ValueError("Unknown report type.")
