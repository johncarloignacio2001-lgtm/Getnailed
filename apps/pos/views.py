from allauth.account.decorators import reauthentication_required
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from apps.accounts.authorization import CAPABILITY_USE_POS
from apps.accounts.decorators import capability_required, owner_required
from apps.services.models import Service

from .forms import CheckoutForm, CheckoutItemFormSet, SaleHistoryFilterForm, VoidSaleForm
from .models import Sale
from .services import create_sale, void_sale


def _appointment_initial(form, appointment_id):
    if not appointment_id:
        return {}, []
    appointment = form.fields["appointment"].queryset.filter(pk=appointment_id).first()
    if appointment is None:
        return {}, []
    items = [
        {
            "service": row.service_id,
            "assigned_staff": appointment.assigned_staff_id,
            "quantity": 1,
        }
        for row in appointment.appointment_services.select_related("service")
        if row.service_id and row.service and row.service.is_active
    ]
    return {"appointment": appointment, "customer": appointment.customer}, items


@capability_required(CAPABILITY_USE_POS)
@require_http_methods(["GET", "POST"])
def index(request):
    form = CheckoutForm(request.POST if request.method == "POST" else None)
    initial_items = []
    if request.method == "GET":
        initial, initial_items = _appointment_initial(form, request.GET.get("appointment"))
        if initial:
            form = CheckoutForm(initial=initial)
    item_formset = CheckoutItemFormSet(
        request.POST if request.method == "POST" else None,
        prefix="items",
        initial=initial_items,
    )
    if request.method == "POST" and form.is_valid() and item_formset.is_valid():
        raw_items = [
            item_form.cleaned_data
            for item_form in item_formset.forms
            if item_form.cleaned_data and item_form.cleaned_data.get("service")
        ]
        try:
            sale = create_sale(
                cashier=request.user,
                raw_items=raw_items,
                customer=form.cleaned_data["customer"],
                appointment=form.cleaned_data["appointment"],
                discount_type=form.cleaned_data["discount_type"],
                discount_value=form.cleaned_data["discount_value"],
                payment_method=form.cleaned_data["payment_method"],
                amount_tendered=form.cleaned_data["amount_tendered"],
                payment_reference=form.cleaned_data["payment_reference"],
                mark_appointment_completed=form.cleaned_data[
                    "mark_appointment_completed"
                ],
            )
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Sale {sale.receipt_number} completed.")
            return redirect("pos:receipt", receipt_number=sale.receipt_number)
    return render(
        request,
        "pos/index.html",
        {
            "form": form,
            "item_formset": item_formset,
            "service_prices": {
                str(pk): str(price)
                for pk, price in Service.objects.filter(is_active=True).values_list(
                    "pk", "price"
                )
            },
        },
    )


@capability_required(CAPABILITY_USE_POS)
def history(request):
    sales = Sale.objects.visible_to(request.user).select_related(
        "customer", "cashier", "payment"
    )
    filter_form = SaleHistoryFilterForm(request.GET or None)
    if filter_form.is_valid():
        query = filter_form.cleaned_data["q"]
        if query:
            sales = sales.filter(
                Q(receipt_number__icontains=query)
                | Q(customer_name_snapshot__icontains=query)
            )
        if filter_form.cleaned_data["date"]:
            sales = sales.filter(created_at__date=filter_form.cleaned_data["date"])
        if filter_form.cleaned_data["status"]:
            sales = sales.filter(status=filter_form.cleaned_data["status"])
    page = Paginator(sales, 30).get_page(request.GET.get("page"))
    return render(request, "pos/history.html", {"page": page, "filter_form": filter_form})


@capability_required(CAPABILITY_USE_POS)
def receipt(request, receipt_number):
    sale = get_object_or_404(
        Sale.objects.visible_to(request.user)
        .select_related("customer", "appointment", "cashier", "payment")
        .prefetch_related("items"),
        receipt_number=receipt_number,
    )
    return render(request, "pos/receipt.html", {"sale": sale})


@owner_required
def void_approval(request):
    sales = Sale.objects.filter(status=Sale.Status.COMPLETED).select_related(
        "cashier", "payment"
    )[:100]
    return render(request, "pos/void_list.html", {"sales": sales})


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def void_detail(request, receipt_number):
    sale = get_object_or_404(
        Sale.objects.select_related("cashier", "payment").prefetch_related("items"),
        receipt_number=receipt_number,
    )
    form = VoidSaleForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            void_sale(sale, actor=request.user, reason=form.cleaned_data["reason"])
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, f"Sale {sale.receipt_number} was voided.")
            return redirect("pos:void_approval")
    return render(request, "pos/void_detail.html", {"sale": sale, "form": form})
