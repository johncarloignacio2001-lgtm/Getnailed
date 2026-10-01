from urllib.parse import urljoin

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.utils import IntegrityError
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.authorization import CAPABILITY_MANAGE_CUSTOMERS
from apps.accounts.decorators import capability_required
from apps.accounts.models import User
from apps.accounts.models import AccountActivation
from apps.accounts.views import BrandedLoginView
from apps.accounts.emails import send_branded_email
from apps.accounts.decorators import owner_required

from .forms import CustomerAccountForm, CustomerForm, CustomerRegistrationForm
from .models import Customer
from apps.bookings.models import Appointment


VISIBLE_APPOINTMENT_STATUSES = tuple(
    value
    for value, _ in Appointment.Status.choices
    if value not in (Appointment.Status.UNVERIFIED, Appointment.Status.EXPIRED)
)


class CustomerLoginView(BrandedLoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        return reverse("core:customer_dashboard")

    def form_valid(self, form):
        user = getattr(form, "user", None)
        if user is None or user.role != User.Role.CUSTOMER:
            form.add_error(None, "This login is for customer accounts only.")
            return self.form_invalid(form)
        return super().form_valid(form)


@require_http_methods(["GET", "POST"])
def register_customer(request):
    form = CustomerRegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=form.cleaned_data["email"],
                    password=form.cleaned_data["password"],
                    first_name=form.cleaned_data["first_name"],
                    last_name=form.cleaned_data["last_name"],
                    phone_number=form.cleaned_data["phone"],
                    role=User.Role.CUSTOMER,
                    is_active=True,
                    is_active_staff_member=False,
                    email_verified_at=timezone.now(),
                )
                Customer.objects.create(
                    user=user,
                    first_name=user.first_name,
                    last_name=user.last_name,
                    email=user.email,
                    phone=form.cleaned_data["phone"],
                )
        except IntegrityError:
            form.add_error("email", "This email is already registered. Please use another email.")
            return render(request, "customers/register.html", {"form": form})
        messages.success(request, "Your account was created. You can now sign in.")
        return redirect("customers:customer_login")
    return render(request, "customers/register.html", {"form": form})


@owner_required
@require_http_methods(["GET", "POST"])
def invite_customer_account(request):
    form = CustomerAccountForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = User.objects.create_user(
                email=form.cleaned_data["email"],
                first_name=form.cleaned_data["first_name"],
                last_name=form.cleaned_data["last_name"],
                phone_number=form.cleaned_data["phone"],
                role=User.Role.CUSTOMER,
                is_active=False,
                is_active_staff_member=False,
            )
            Customer.objects.create(
                user=user,
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                phone=form.cleaned_data["phone"],
            )
            activation, token = AccountActivation.issue(user)
            activation_path = reverse(
                "accounts:activate",
                kwargs={"public_id": activation.public_id, "token": token},
            )
            activation_url = (
                urljoin(f"{settings.PUBLIC_BASE_URL.rstrip('/')}/", activation_path.lstrip("/"))
                if settings.PUBLIC_BASE_URL
                else request.build_absolute_uri(activation_path)
            )
            send_branded_email(
                user.email,
                f"Activate your {settings.BRAND_NAME} customer account",
                "accounts/emails/activation",
                {"user": user, "activation_url": activation_url, "expires_at": activation.expires_at},
            )
        return redirect("customers:invite_customer")
    return render(request, "customers/invite_customer.html", {"form": form})


def _visible_customers():
    return Customer.objects.filter(
        Q(appointments__isnull=True) | Q(appointments__status__in=VISIBLE_APPOINTMENT_STATUSES)
    ).distinct()


@capability_required(CAPABILITY_MANAGE_CUSTOMERS)
def index(request):
    customers = _visible_customers()
    query = request.GET.get("q", "").strip()
    if query:
        customers = customers.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
            | Q(phone__icontains=query)
        )
    page = Paginator(customers, 25).get_page(request.GET.get("page"))
    return render(request, "customers/index.html", {"page": page, "query": query})


@capability_required(CAPABILITY_MANAGE_CUSTOMERS)
@require_http_methods(["GET", "POST"])
def detail(request, pk):
    customer = get_object_or_404(
        _visible_customers().prefetch_related(
            Prefetch(
                "appointments",
                queryset=Appointment.objects.filter(
                    status__in=VISIBLE_APPOINTMENT_STATUSES
                ).prefetch_related("appointment_services"),
            )
        ),
        pk=pk,
    )
    form = CustomerForm(request.POST if request.method == "POST" else None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("customers:detail", pk=customer.pk)
    return render(
        request,
        "customers/detail.html",
        {"customer": customer, "form": form},
    )
