from datetime import datetime, time, timedelta
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from .models import StaffSchedule, StaffTimeBlock

DEFAULT_START_TIME = "09:00:00"
DEFAULT_END_TIME = "21:00:00"
DEFAULT_LUNCH_START = "12:00:00"
DEFAULT_LUNCH_END = "13:00:00"

# Staggered leave assignment: Every staff member has exactly 1 day off (leave) per week,
# ensuring full coverage across all specialties and cashiers from Monday to Sunday.
DEFAULT_STAFF_LEAVE_ASSIGNMENTS = {
    "nory.pecaso@getnailed.com": StaffSchedule.DayOfWeek.MONDAY,
    "phen.abino@getnailed.com": StaffSchedule.DayOfWeek.MONDAY,
    "rita.inoferio@getnailed.com": StaffSchedule.DayOfWeek.TUESDAY,
    "sheng.lucilla@getnailed.com": StaffSchedule.DayOfWeek.TUESDAY,
    "stef.datur@getnailed.com": StaffSchedule.DayOfWeek.WEDNESDAY,
    "ann.olarte@getnailed.com": StaffSchedule.DayOfWeek.WEDNESDAY,
    "alona.delacruz@getnailed.com": StaffSchedule.DayOfWeek.THURSDAY,
    "aila.ramos@getnailed.com": StaffSchedule.DayOfWeek.THURSDAY,
    "jessa.manuel@getnailed.com": StaffSchedule.DayOfWeek.FRIDAY,
    "manilyn.brigais@getnailed.com": StaffSchedule.DayOfWeek.SATURDAY,
    "verna.agustin@getnailed.com": StaffSchedule.DayOfWeek.SUNDAY,
}


def apply_staff_weekly_schedules():
    """Configure weekly schedules (Mon-Sun) for all active staff.
    Each staff member works 6 days with lunch 12:00 PM - 1:00 PM and gets 1 day leave/off.
    """
    staff_members = list(
        User.objects.filter(role=User.Role.STAFF, is_active=True).order_by("pk")
    )
    if not staff_members:
        return 0

    updated_count = 0
    with transaction.atomic():
        for idx, staff in enumerate(staff_members):
            email_key = (staff.email or "").lower()
            if email_key in DEFAULT_STAFF_LEAVE_ASSIGNMENTS:
                leave_day = DEFAULT_STAFF_LEAVE_ASSIGNMENTS[email_key]
            else:
                # Fallback: distribute across weekdays (0 to 6)
                leave_day = idx % 7

            for day_idx in range(7):
                is_working = day_idx != leave_day
                StaffSchedule.objects.update_or_create(
                    staff=staff,
                    day_of_week=day_idx,
                    defaults={
                        "start_time": DEFAULT_START_TIME,
                        "end_time": DEFAULT_END_TIME,
                        "lunch_start": DEFAULT_LUNCH_START,
                        "lunch_end": DEFAULT_LUNCH_END,
                        "is_working": is_working,
                    },
                )
                updated_count += 1

    return updated_count


def sync_staff_time_blocks(ref_date=None, weeks=4):
    """Generate or update visual calendar time blocks for lunch breaks (12pm-1pm)
    and scheduled leave days based on each staff member's StaffSchedule.
    Populates weeks into the future so the owner admin visual calendar displays them.
    """
    if ref_date is None:
        ref_date = timezone.localdate()

    # Align to Sunday of current week
    week_start = ref_date - timedelta(days=(ref_date.weekday() + 1) % 7)
    total_days = weeks * 7

    active_staff = list(
        User.objects.filter(role=User.Role.STAFF, is_active=True)
        .prefetch_related("schedules")
        .order_by("pk")
    )
    if not active_staff:
        return 0

    created_or_updated = 0
    t_lunch_start = datetime.strptime(DEFAULT_LUNCH_START, "%H:%M:%S").time()
    t_lunch_end = datetime.strptime(DEFAULT_LUNCH_END, "%H:%M:%S").time()
    t_shift_start = datetime.strptime(DEFAULT_START_TIME, "%H:%M:%S").time()
    t_shift_end = datetime.strptime(DEFAULT_END_TIME, "%H:%M:%S").time()

    with transaction.atomic():
        for day_offset in range(total_days):
            current_date = week_start + timedelta(days=day_offset)
            current_weekday = current_date.weekday()

            for staff in active_staff:
                sched = next(
                    (s for s in staff.schedules.all() if s.day_of_week == current_weekday),
                    None,
                )
                if sched is None:
                    continue

                if sched.is_working:
                    # Clean up any full-day leave block on a working day
                    StaffTimeBlock.objects.filter(
                        staff=staff,
                        date=current_date,
                        reason__icontains="leave",
                    ).delete()

                    # Ensure Lunch block 12:00 PM - 1:00 PM
                    l_start = sched.lunch_start or t_lunch_start
                    l_end = sched.lunch_end or t_lunch_end

                    block, _ = StaffTimeBlock.objects.get_or_create(
                        staff=staff,
                        date=current_date,
                        start_time=l_start,
                        end_time=l_end,
                        defaults={"reason": "Lunch"},
                    )
                    created_or_updated += 1
                else:
                    # Staff is on leave today (Day Off)
                    # Clean up any lunch blocks on an off day
                    StaffTimeBlock.objects.filter(
                        staff=staff,
                        date=current_date,
                        reason__icontains="lunch",
                    ).delete()

                    # Ensure scheduled leave block covering the shift
                    block, _ = StaffTimeBlock.objects.get_or_create(
                        staff=staff,
                        date=current_date,
                        start_time=sched.start_time or t_shift_start,
                        end_time=sched.end_time or t_shift_end,
                        defaults={"reason": "Leave"},
                    )
                    created_or_updated += 1

    return created_or_updated

