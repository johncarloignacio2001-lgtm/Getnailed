from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from allauth.account.decorators import reauthentication_required

from apps.accounts.authorization import is_owner
from apps.accounts.decorators import cashier_or_owner_required, owner_required

from .forms import (
    ServiceCategoryForm,
    ServiceFilterForm,
    ServiceForm,
    StaffProfileFilterForm,
    StaffProfileForm,
)
from .models import Service, ServiceCategory, StaffProfile


@cashier_or_owner_required
@require_http_methods(["GET"])
def index(request):
    owner = is_owner(request.user)
    filter_form = ServiceFilterForm(
        request.GET,
        include_inactive=owner,
    )
    services = Service.objects.select_related("category")
    if not owner:
        services = services.filter(is_active=True)
    if filter_form.is_valid():
        query = filter_form.cleaned_data["q"]
        category = filter_form.cleaned_data["category"]
        status = filter_form.cleaned_data["status"]
        if query:
            services = services.filter(
                Q(name__icontains=query) | Q(description__icontains=query)
            )
        if category:
            services = services.filter(category=category)
        if owner and status == "active":
            services = services.filter(is_active=True)
        elif owner and status == "inactive":
            services = services.filter(is_active=False)
    page_obj = Paginator(services, 12).get_page(request.GET.get("page"))
    return render(
        request,
        "services/index.html",
        {"filter_form": filter_form, "page_obj": page_obj, "owner_view": owner},
    )


@owner_required
@require_http_methods(["GET"])
def category_list(request):
    query = request.GET.get("q", "")[:100].strip()
    categories = ServiceCategory.objects.annotate(service_count=Count("services")).order_by("name")
    if query:
        categories = categories.filter(name__icontains=query)
    page_obj = Paginator(categories, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "services/category_list.html",
        {"page_obj": page_obj, "query": query},
    )


def _save_model_form(request, form, success_message, redirect_name):
    if form.is_valid():
        form.save()
        messages.success(request, success_message)
        return redirect(redirect_name)
    return None


@owner_required
@require_http_methods(["GET", "POST"])
def category_create(request):
    form = ServiceCategoryForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Service category created.", "services:category_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "New category", "cancel_url": "services:category_list"},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def category_update(request, pk):
    category = get_object_or_404(ServiceCategory, pk=pk)
    form = ServiceCategoryForm(
        request.POST if request.method == "POST" else None,
        instance=category,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Service category updated.", "services:category_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "Edit category", "cancel_url": "services:category_list"},
    )


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def category_delete(request, pk):
    category = get_object_or_404(ServiceCategory, pk=pk)
    if request.method == "POST":
        try:
            category.delete()
        except ProtectedError:
            messages.error(request, "Move or delete this category's services first.")
        else:
            messages.success(request, "Service category deleted.")
        return redirect("services:category_list")
    return render(
        request,
        "services/confirm_delete.html",
        {
            "object": category,
            "title": "Delete category",
            "cancel_url": "services:category_list",
        },
    )


@owner_required
@require_http_methods(["GET", "POST"])
def service_create(request):
    form = ServiceForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        actor=request.user,
    )
    response = _save_model_form(request, form, "Service created.", "services:index")
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "New service", "cancel_url": "services:index"},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def service_update(request, pk):
    service = get_object_or_404(Service.objects.select_related("category"), pk=pk)
    form = ServiceForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        instance=service,
        actor=request.user,
    )
    response = _save_model_form(request, form, "Service updated.", "services:index")
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "Edit service", "cancel_url": "services:index"},
    )


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if request.method == "POST":
        service.delete()
        messages.success(request, "Service deleted.")
        return redirect("services:index")
    return render(
        request,
        "services/confirm_delete.html",
        {"object": service, "title": "Delete service", "cancel_url": "services:index"},
    )


@owner_required
@require_http_methods(["GET"])
def staff_list(request):
    filter_form = StaffProfileFilterForm(request.GET)
    profiles = StaffProfile.objects.select_related("user")
    if filter_form.is_valid():
        query = filter_form.cleaned_data["q"]
        availability = filter_form.cleaned_data["availability"]
        status = filter_form.cleaned_data["status"]
        if query:
            profiles = profiles.filter(
                Q(user__first_name__icontains=query)
                | Q(user__last_name__icontains=query)
                | Q(user__email__icontains=query)
                | Q(specialty__icontains=query)
            )
        if availability:
            profiles = profiles.filter(availability_status=availability)
        if status == "active":
            profiles = profiles.filter(is_active=True)
        elif status == "inactive":
            profiles = profiles.filter(is_active=False)
    page_obj = Paginator(profiles, 15).get_page(request.GET.get("page"))
    return render(
        request,
        "services/staff_list.html",
        {"filter_form": filter_form, "page_obj": page_obj},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def staff_create(request):
    form = StaffProfileForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Staff profile created.", "services:staff_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "New staff profile", "cancel_url": "services:staff_list"},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def staff_update(request, pk):
    profile = get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)
    form = StaffProfileForm(
        request.POST if request.method == "POST" else None,
        instance=profile,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Staff profile updated.", "services:staff_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "Edit staff profile", "cancel_url": "services:staff_list"},
    )


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def staff_delete(request, pk):
    profile = get_object_or_404(StaffProfile.objects.select_related("user"), pk=pk)
    if request.method == "POST":
        profile.delete()
        messages.success(request, "Staff profile deleted. The user account was not deleted.")
        return redirect("services:staff_list")
    return render(
        request,
        "services/confirm_delete.html",
        {
            "object": profile,
            "title": "Delete staff profile",
            "cancel_url": "services:staff_list",
        },
    )
