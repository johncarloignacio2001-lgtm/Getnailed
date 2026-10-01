from django.db.models import Q


CAPABILITY_USE_POS = "use_pos"
CAPABILITY_MANAGE_BOOKINGS = "manage_bookings"
CAPABILITY_MANAGE_CUSTOMERS = "manage_customers"
CAPABILITY_ASSIGN_SERVICES = "assign_services"
CAPABILITY_VIEW_MONITORING = "view_monitoring"
CAPABILITY_VIEW_DAILY_SUMMARY = "view_daily_summary"


def is_owner(user):
    return bool(user.is_authenticated and (user.is_superuser or user.is_owner))


def is_cashier_or_owner(user):
    return bool(is_owner(user) or (user.is_authenticated and user.is_cashier))


def is_staff(user):
    return bool(is_owner(user) or (user.is_authenticated and user.is_service_staff))


def is_internal_user(user):
    return bool(
        user.is_authenticated
        and (is_owner(user) or user.is_cashier or user.is_service_staff)
    )


def is_customer(user):
    return bool(user.is_authenticated and user.is_customer)


def has_capability(user, capability):
    if is_owner(user):
        return True
    if not is_internal_user(user):
        return False
    if capability == CAPABILITY_USE_POS:
        return user.is_cashier or (user.is_service_staff and user.can_use_pos)
    if capability == CAPABILITY_MANAGE_BOOKINGS:
        return user.is_cashier or (user.is_service_staff and user.can_manage_bookings)
    if capability == CAPABILITY_MANAGE_CUSTOMERS:
        return user.is_cashier or (user.is_service_staff and user.can_manage_customers)
    if capability == CAPABILITY_ASSIGN_SERVICES:
        return user.is_cashier or (user.is_service_staff and user.can_assign_services)
    if capability == CAPABILITY_VIEW_MONITORING:
        return user.is_cashier or user.is_service_staff
    if capability == CAPABILITY_VIEW_DAILY_SUMMARY:
        return user.is_cashier
    raise ValueError(f"Unknown capability: {capability}")


def scope_owned_or_assigned(
    queryset,
    user,
    *,
    owner_field,
    assignment_field=None,
    management_capability=None,
):
    """Scope first, then resolve URL IDs from the returned queryset."""
    if is_owner(user):
        return queryset
    if not user.is_authenticated:
        return queryset.none()
    if management_capability and has_capability(user, management_capability):
        return queryset
    filters = Q(**{owner_field: user})
    if assignment_field and user.is_service_staff:
        filters |= Q(**{assignment_field: user})
    return queryset.filter(filters)
