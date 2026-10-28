from allauth.mfa.base import views as base_views
from django.urls import path

from .views import (
    SecureActivateTOTPView,
    SecureDeactivateTOTPView,
    recovery_codes,
    regenerate_recovery_codes,
)


class BrandedMFAAuthenticateView(base_views.AuthenticateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        if self.request.user.is_authenticated:
            try:
                from allauth.account.internal.flows.reauthentication import record_authentication
                record_authentication(self.request, self.request.user, method="mfa", reauthenticated=True)
            except Exception:
                pass
        return response


urlpatterns = [
    path("", base_views.index, name="mfa_index"),
    path("authenticate/", BrandedMFAAuthenticateView.as_view(), name="mfa_authenticate"),
    path("reauthenticate/", base_views.reauthenticate, name="mfa_reauthenticate"),
    path("totp/activate/", SecureActivateTOTPView.as_view(), name="mfa_activate_totp"),
    path("totp/deactivate/", SecureDeactivateTOTPView.as_view(), name="mfa_deactivate_totp"),
    path("recovery-codes/", recovery_codes, name="mfa_recovery_codes"),
    path(
        "recovery-codes/regenerate/",
        regenerate_recovery_codes,
        name="mfa_regenerate_recovery_codes",
    ),
]
