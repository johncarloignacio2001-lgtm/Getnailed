from datetime import datetime, timedelta
from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from allauth.account.decorators import reauthentication_required

from apps.accounts.authorization import is_owner
from apps.accounts.decorators import cashier_or_owner_required, owner_required
from apps.accounts.models import User

from .forms import (
    ServiceCategoryForm,
    ServiceFilterForm,
    ServiceForm,
    StaffProfileFilterForm,
    StaffProfileForm,
    StaffScheduleForm,
    StaffTimeBlockForm,
)
from .models import (
    Service,
    ServiceCategory,
    StaffProfile,
    StaffSchedule,
    StaffTimeBlock,
)


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
        specialty = filter_form.cleaned_data.get("specialty")
        if specialty:
            if specialty == "CASHIER":
                profiles = profiles.filter(
                    Q(user__can_use_pos=True) | Q(specialty__icontains="Cashier")
                )
            elif specialty == "WAX":
                profiles = profiles.filter(
                    Q(specialty__icontains="Wax") | Q(specialty__icontains="Threading")
                )
            elif specialty == "LASH":
                profiles = profiles.filter(
                    Q(specialty__icontains="Lash")
                )
            elif specialty == "NAIL ART":
                profiles = profiles.filter(
                    Q(specialty__icontains="Nail Art")
                )
            elif specialty == "FOOTSPA":
                profiles = profiles.filter(
                    Q(specialty__icontains="Foot Spa") | Q(specialty__icontains="Footspa")
                )
            elif specialty == "THERAPIST":
                profiles = profiles.filter(
                    Q(specialty__icontains="Therapist")
                )
            elif specialty == "NAIL TECH":
                profiles = profiles.filter(
                    Q(specialty__icontains="Nail Tech")
                )
            else:
                profiles = profiles.filter(specialty__icontains=specialty)
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


# ---------------------------------------------------------------------------
# Staff Schedules (Working Shifts)
# ---------------------------------------------------------------------------

@owner_required
@require_http_methods(["GET", "POST"])
def schedule_list(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "sync_time_blocks":
            from .schedules import sync_staff_time_blocks
            count = sync_staff_time_blocks(weeks=4)
            messages.success(request, f"Successfully synchronized {count} calendar time blocks (Lunch & Leave) for the visual planner.")
            return redirect("services:schedule_list")
        elif action == "apply_default_roster":
            from .schedules import apply_staff_weekly_schedules, sync_staff_time_blocks
            apply_staff_weekly_schedules()
            count = sync_staff_time_blocks(weeks=4)
            messages.success(request, f"Re-applied standard roster (Mon-Sun, 1 day leave per staff, 12pm-1pm lunch) and synchronized {count} time blocks.")
            return redirect("services:schedule_list")

    schedules = StaffSchedule.objects.select_related("staff", "staff__staff_profile").order_by(
        "staff__first_name", "staff__last_name", "day_of_week"
    )
    staff_id = request.GET.get("staff")
    if staff_id and staff_id.isdigit():
        schedules = schedules.filter(staff_id=int(staff_id))

    day_param = request.GET.get("day")
    if day_param is not None and day_param.isdigit() and 0 <= int(day_param) <= 6:
        schedules = schedules.filter(day_of_week=int(day_param))

    status_param = request.GET.get("status")
    if status_param == "working":
        schedules = schedules.filter(is_working=True)
    elif status_param in ("off", "leave"):
        schedules = schedules.filter(is_working=False)

    staff_list = User.objects.filter(role=User.Role.STAFF, is_active=True).order_by("first_name", "last_name")
    page_obj = Paginator(schedules, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "services/schedule_list.html",
        {
            "page_obj": page_obj,
            "staff_id": staff_id,
            "staff_list": staff_list,
            "day_param": day_param,
            "status_param": status_param,
            "day_choices": StaffSchedule.DayOfWeek.choices,
            "total_staff_count": staff_list.count(),
            "working_count": StaffSchedule.objects.filter(is_working=True).count(),
            "leave_count": StaffSchedule.objects.filter(is_working=False).count(),
        },
    )


@owner_required
@require_http_methods(["GET", "POST"])
def schedule_create(request):
    form = StaffScheduleForm(
        request.POST if request.method == "POST" else None,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Staff shift schedule created.", "services:schedule_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "New staff schedule", "cancel_url": "services:schedule_list"},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def schedule_update(request, pk):
    schedule = get_object_or_404(StaffSchedule.objects.select_related("staff"), pk=pk)
    form = StaffScheduleForm(
        request.POST if request.method == "POST" else None,
        instance=schedule,
        actor=request.user,
    )
    response = _save_model_form(
        request, form, "Staff shift schedule updated.", "services:schedule_list"
    )
    if response:
        return response
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "Edit staff schedule", "cancel_url": "services:schedule_list"},
    )


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def schedule_delete(request, pk):
    schedule = get_object_or_404(StaffSchedule.objects.select_related("staff"), pk=pk)
    if request.method == "POST":
        schedule.delete()
        messages.success(request, "Staff schedule deleted.")
        return redirect("services:schedule_list")
    return render(
        request,
        "services/confirm_delete.html",
        {
            "object": schedule,
            "title": "Delete staff schedule",
            "cancel_url": "services:schedule_list",
        },
    )


# ---------------------------------------------------------------------------
# Staff Time Blocks (Visual Weekly Grid & Management)
# ---------------------------------------------------------------------------

ROW_HEIGHT = 56
START_HOUR = 9
END_HOUR = 22


def _get_week_start(ref_date):
    # Sunday as first day of week
    return ref_date - timedelta(days=(ref_date.weekday() + 1) % 7)


def _get_block_color_class(reason):
    r = (reason or "").lower().strip()
    if any(k in r for k in ("lunch", "personal", "admin", "break", "finish", "rest", "errand", "meal", "snack")):
        return "block-color-lime"
    elif any(k in r for k in ("leave", "sick", "doctor", "medical", "off", "vacation", "emergency")):
        return "block-color-rose"
    else:
        return "block-color-blue"


def _layout_day_blocks(day_raw_blocks, grid_start_min, grid_end_min):
    prepared = []
    for b in day_raw_blocks:
        s_min = b.start_time.hour * 60 + b.start_time.minute
        e_min = b.end_time.hour * 60 + b.end_time.minute
        eff_s = max(grid_start_min, s_min)
        eff_e = min(grid_end_min, e_min)
        if eff_e <= eff_s:
            continue
        top_px = ((eff_s - grid_start_min) / 60) * ROW_HEIGHT
        height_px = max(24, ((eff_e - eff_s) / 60) * ROW_HEIGHT)
        color_class = _get_block_color_class(b.reason)
        prepared.append({
            "obj": b,
            "id": b.pk,
            "staff_id": b.staff_id,
            "staff_name": b.staff.get_full_name() or b.staff.email,
            "date_iso": b.date.isoformat(),
            "start_time_iso": b.start_time.strftime("%H:%M"),
            "end_time_iso": b.end_time.strftime("%H:%M"),
            "start_time_display": b.start_time.strftime("%I:%M %p").lstrip("0"),
            "end_time_display": b.end_time.strftime("%I:%M %p").lstrip("0"),
            "reason": b.reason or "Time block",
            "top_px": int(top_px),
            "height_px": int(height_px),
            "color_class": color_class,
            "eff_s": eff_s,
            "eff_e": eff_e,
        })

    if not prepared:
        return []

    # Sort blocks by start time, and longer duration first
    prepared.sort(key=lambda item: (item["eff_s"], -item["eff_e"]))

    # Group into connected overlapping clusters
    clusters = []
    current_cluster = []
    cluster_end = -1

    for item in prepared:
        if not current_cluster:
            current_cluster.append(item)
            cluster_end = item["eff_e"]
        else:
            if item["eff_s"] < cluster_end:
                current_cluster.append(item)
                cluster_end = max(cluster_end, item["eff_e"])
            else:
                clusters.append(current_cluster)
                current_cluster = [item]
                cluster_end = item["eff_e"]
    if current_cluster:
        clusters.append(current_cluster)

    # Assign columns within each cluster (Greedy interval coloring)
    for cluster in clusters:
        columns = []
        for item in cluster:
            placed = False
            for col_idx, col_last_end in enumerate(columns):
                if item["eff_s"] >= col_last_end:
                    columns[col_idx] = item["eff_e"]
                    item["col_idx"] = col_idx
                    placed = True
                    break
            if not placed:
                item["col_idx"] = len(columns)
                columns.append(item["eff_e"])

        num_cols = max(1, len(columns))
        for item in cluster:
            item["num_cols"] = num_cols
            item["left_pct"] = round((item["col_idx"] / num_cols) * 100, 2)
            item["width_pct"] = round((100 / num_cols), 2)

    return prepared


@owner_required
@require_http_methods(["GET"])
def time_block_list(request):
    today = timezone.localdate()
    date_param = request.GET.get("date") or request.GET.get("week")
    ref_date = today
    if date_param:
        try:
            ref_date = datetime.strptime(date_param.strip(), "%Y-%m-%d").date()
        except (ValueError, TypeError):
            ref_date = today

    week_start = _get_week_start(ref_date)
    week_end = week_start + timedelta(days=6)
    prev_week_date = week_start - timedelta(days=7)
    next_week_date = week_start + timedelta(days=7)

    staff_id = request.GET.get("staff")
    selected_staff = None
    if staff_id and staff_id.isdigit():
        selected_staff = User.objects.filter(role=User.Role.STAFF, pk=int(staff_id)).first()

    staff_list = User.objects.filter(role=User.Role.STAFF, is_active=True).order_by("first_name", "last_name")

    # Table view data (preserves pagination & existing table list)
    blocks_qs = StaffTimeBlock.objects.select_related("staff").order_by("-date", "start_time")
    if selected_staff:
        blocks_qs = blocks_qs.filter(staff=selected_staff)
    page_obj = Paginator(blocks_qs, 20).get_page(request.GET.get("page"))

    # Grid view data
    week_blocks_qs = StaffTimeBlock.objects.filter(
        date__range=(week_start, week_end)
    ).select_related("staff").order_by("date", "start_time")
    if selected_staff:
        week_blocks_qs = week_blocks_qs.filter(staff=selected_staff)

    grid_start_min = START_HOUR * 60
    grid_end_min = END_HOUR * 60
    total_grid_height = (END_HOUR - START_HOUR) * ROW_HEIGHT

    day_columns = []
    for i in range(7):
        current_date = week_start + timedelta(days=i)
        day_raw_blocks = [b for b in week_blocks_qs if b.date == current_date]
        day_blocks = _layout_day_blocks(day_raw_blocks, grid_start_min, grid_end_min)
        day_columns.append({
            "date": current_date,
            "date_iso": current_date.isoformat(),
            "day_name": current_date.strftime("%A"),
            "day_short": current_date.strftime("%a"),
            "is_today": current_date == today,
            "blocks": day_blocks,
        })

    hours_display = [
        {"hour": h, "label": f"{h % 12 or 12} {'am' if h < 12 else 'pm'}"}
        for h in range(START_HOUR, END_HOUR)
    ]

    add_form = StaffTimeBlockForm(
        initial={"staff": selected_staff, "date": today, "start_time": "09:00", "end_time": "10:00"},
        actor=request.user,
    )

    view_mode = request.GET.get("view", "grid")

    return render(
        request,
        "services/time_block_list.html",
        {
            "page_obj": page_obj,
            "staff_id": str(selected_staff.pk) if selected_staff else "",
            "selected_staff": selected_staff,
            "staff_list": staff_list,
            "today": today,
            "week_start": week_start,
            "week_end": week_end,
            "prev_week_date": prev_week_date.isoformat(),
            "next_week_date": next_week_date.isoformat(),
            "current_week_date": today.isoformat(),
            "day_columns": day_columns,
            "hours_display": hours_display,
            "row_height": ROW_HEIGHT,
            "total_grid_height": total_grid_height,
            "add_form": add_form,
            "view_mode": view_mode,
        },
    )


@owner_required
@require_http_methods(["GET", "POST"])
def time_block_create(request):
    if request.method == "POST":
        post_data = request.POST

        # 1. Staff selection (support single, multiple, or all active technicians)
        staff_input = post_data.getlist("staff")
        apply_all_staff = post_data.get("all_staff") in ("true", "1", "on") or "all" in staff_input

        active_staff_qs = User.objects.filter(role=User.Role.STAFF, is_active=True)
        if apply_all_staff:
            target_staff_list = list(active_staff_qs)
        else:
            staff_pks = [int(s) for s in staff_input if str(s).isdigit()]
            target_staff_list = list(active_staff_qs.filter(pk__in=staff_pks))

        if not target_staff_list:
            messages.error(request, "Please select at least one active technician.")
            return redirect("services:time_block_list")

        # 2. Date parsing (support primary date + multi-day repeat_dates)
        date_str = post_data.get("date", "").strip()
        try:
            primary_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            messages.error(request, "Invalid date provided.")
            return redirect("services:time_block_list")

        target_dates = [primary_date]
        for extra_date_str in post_data.getlist("repeat_dates"):
            try:
                extra_date = datetime.strptime(extra_date_str.strip(), "%Y-%m-%d").date()
                if extra_date not in target_dates:
                    target_dates.append(extra_date)
            except (ValueError, TypeError):
                pass

        # 3. Time slots (supports multiple rows with minute precision)
        start_times = post_data.getlist("start_time")
        end_times = post_data.getlist("end_time")
        reasons = post_data.getlist("reason")

        slots_to_create = []
        errors = []
        max_rows = max(len(start_times), len(end_times), len(reasons), 1)

        for idx in range(max_rows):
            s_str = start_times[idx].strip() if idx < len(start_times) else ""
            e_str = end_times[idx].strip() if idx < len(end_times) else ""
            r_str = reasons[idx].strip() if idx < len(reasons) else "Work Time"

            if not s_str or not e_str:
                continue

            try:
                s_time = datetime.strptime(s_str[:5], "%H:%M").time()
                e_time = datetime.strptime(e_str[:5], "%H:%M").time()
            except ValueError:
                errors.append(f"Invalid time in slot #{idx + 1}: {s_str} - {e_str}")
                continue

            if e_time <= s_time:
                errors.append(
                    f"Slot #{idx + 1}: End time ({e_time.strftime('%I:%M %p')}) must be after start time ({s_time.strftime('%I:%M %p')})."
                )
                continue

            slots_to_create.append({
                "start_time": s_time,
                "end_time": e_time,
                "reason": r_str[:200] if r_str else "Time block",
            })

        if errors:
            for err in errors:
                messages.error(request, err)
            return redirect("services:time_block_list")

        if not slots_to_create:
            messages.error(request, "Please enter at least one valid time block.")
            return redirect("services:time_block_list")

        # 4. Atomic batch creation
        created_blocks = []
        with transaction.atomic():
            for d in target_dates:
                for staff_obj in target_staff_list:
                    for slot in slots_to_create:
                        created_blocks.append(
                            StaffTimeBlock(
                                staff=staff_obj,
                                date=d,
                                start_time=slot["start_time"],
                                end_time=slot["end_time"],
                                reason=slot["reason"],
                            )
                        )
            StaffTimeBlock.objects.bulk_create(created_blocks)

        created_count = len(created_blocks)
        if created_count == 1:
            messages.success(request, "Staff time block created.")
        else:
            messages.success(
                request,
                f"Successfully created {created_count} time blocks ({len(slots_to_create)} slot(s) × {len(target_staff_list)} technician(s) × {len(target_dates)} day(s)).",
            )

        return redirect("services:time_block_list")

    form = StaffTimeBlockForm(actor=request.user)
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "New time block / break", "cancel_url": "services:time_block_list"},
    )


@owner_required
@require_http_methods(["GET", "POST"])
def time_block_update(request, pk):
    block = get_object_or_404(StaffTimeBlock.objects.select_related("staff"), pk=pk)
    form = StaffTimeBlockForm(
        request.POST if request.method == "POST" else None,
        instance=block,
        actor=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Staff time block updated.")
        return redirect("services:time_block_list")
    return render(
        request,
        "services/model_form.html",
        {"form": form, "title": "Edit time block / break", "cancel_url": "services:time_block_list"},
    )


@owner_required
@reauthentication_required
@require_http_methods(["GET", "POST"])
def time_block_delete(request, pk):
    block = get_object_or_404(StaffTimeBlock.objects.select_related("staff"), pk=pk)
    if request.method == "POST":
        block.delete()
        messages.success(request, "Staff time block deleted.")
        return redirect("services:time_block_list")
    return render(
        request,
        "services/confirm_delete.html",
        {
            "object": block,
            "title": "Delete staff time block",
            "cancel_url": "services:time_block_list",
        },
    )




