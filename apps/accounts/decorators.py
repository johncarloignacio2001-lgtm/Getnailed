from functools import wraps

from django.conf import settings
from django.contrib.auth.mixins import AccessMixin
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .authorization import (
    has_capability,
    is_cashier_or_owner,
    is_customer,
    is_internal_user,
    is_owner,
    is_staff,
)


def permission_required(predicate):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                from apps.audittrail.events import record_security_event
                from apps.audittrail.models import SecurityEvent

                record_security_event(
                    SecurityEvent.Action.UNAUTHORIZED_ACCESS,
                    request=request,
                    target_type="path",
                    target_id=request.path,
                    result=SecurityEvent.Result.FAILURE,
                )
                return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
            if not predicate(request.user):
                from apps.audittrail.events import record_security_event
                from apps.audittrail.models import SecurityEvent

                record_security_event(
                    SecurityEvent.Action.UNAUTHORIZED_ACCESS,
                    request=request,
                    user=request.user,
                    target_type="path",
                    target_id=request.path,
                    result=SecurityEvent.Result.FAILURE,
                )
                raise PermissionDenied("You do not have permission to access this page.")
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator


owner_required = permission_required(is_owner)
cashier_or_owner_required = permission_required(is_cashier_or_owner)
staff_required = permission_required(is_staff)
authenticated_internal_user_required = permission_required(is_internal_user)
customer_required = permission_required(is_customer)


def capability_required(capability):
    return permission_required(lambda user: has_capability(user, capability))


def role_required(*roles):
    return permission_required(
        lambda user: is_owner(user) or (user.is_authenticated and user.role in roles)
    )


class PredicateRequiredMixin(AccessMixin):
    permission_predicate = None

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            from apps.audittrail.events import record_security_event
            from apps.audittrail.models import SecurityEvent

            record_security_event(
                SecurityEvent.Action.UNAUTHORIZED_ACCESS,
                request=request,
                target_type="path",
                target_id=request.path,
                result=SecurityEvent.Result.FAILURE,
            )
            return self.handle_no_permission()
        if self.permission_predicate is None or not self.permission_predicate(request.user):
            from apps.audittrail.events import record_security_event
            from apps.audittrail.models import SecurityEvent

            record_security_event(
                SecurityEvent.Action.UNAUTHORIZED_ACCESS,
                request=request,
                user=request.user,
                target_type="path",
                target_id=request.path,
                result=SecurityEvent.Result.FAILURE,
            )
            raise PermissionDenied("You do not have permission to access this page.")
        return super().dispatch(request, *args, **kwargs)


class OwnerRequiredMixin(PredicateRequiredMixin):
    permission_predicate = staticmethod(is_owner)


class CashierOrOwnerRequiredMixin(PredicateRequiredMixin):
    permission_predicate = staticmethod(is_cashier_or_owner)


class StaffRequiredMixin(PredicateRequiredMixin):
    permission_predicate = staticmethod(is_staff)


class InternalUserRequiredMixin(PredicateRequiredMixin):
    permission_predicate = staticmethod(is_internal_user)


class CapabilityRequiredMixin(PredicateRequiredMixin):
    required_capability = None

    def dispatch(self, request, *args, **kwargs):
        if not self.required_capability:
            raise ValueError("required_capability must be configured")
        self.permission_predicate = lambda user: has_capability(
            user, self.required_capability
        )
        return super().dispatch(request, *args, **kwargs)
