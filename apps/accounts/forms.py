from django import forms
from allauth.account.forms import LoginForm
from allauth.mfa.base.forms import AuthenticateForm, ReauthenticateForm
from allauth.mfa.base.internal.flows import check_rate_limit
from allauth.mfa.models import Authenticator
from allauth.core import context
from captcha.fields import CaptchaField
from django.conf import settings
from django.contrib.auth.forms import (
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.cache import cache
from django.core.exceptions import ValidationError

from .models import MFAConfiguration, MFARecoveryCode, User
from .login_security import login_requires_captcha
from .authorization import is_owner


FORM_CONTROL = {"class": "form-control"}
class BrandedAllauthLoginForm(LoginForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["login"].label = "Email address"
        self.fields["login"].max_length = 254
        self.fields["login"].widget = forms.EmailInput(
            attrs={
                **FORM_CONTROL,
                "autocomplete": "email",
                "placeholder": "Email address",
                "maxlength": "254",
            }
        )
        self.fields["password"].max_length = 128
        self.fields["password"].widget.attrs.update(
            {
                **FORM_CONTROL,
                "autocomplete": "current-password",
                "placeholder": "Password",
                "maxlength": "128",
            }
        )
        if "remember" in self.fields:
            self.fields["remember"].widget.attrs.update({"class": "form-check-input"})
        login_value = self.data.get("login") if self.is_bound else None
        if login_requires_captcha(self.request, login_value):
            self.fields["captcha"] = CaptchaField(label="Security check")
            self.fields["captcha"].widget.widgets[1].attrs.update(FORM_CONTROL)


class InternalAccountInvitationForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=((User.Role.CASHIER, "Cashier"), (User.Role.STAFF, "Staff")),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone_number", "role")
        widgets = {
            "first_name": forms.TextInput(attrs=FORM_CONTROL),
            "last_name": forms.TextInput(attrs=FORM_CONTROL),
            "email": forms.EmailInput(attrs=FORM_CONTROL),
            "phone_number": forms.TextInput(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not self.actor or not is_owner(self.actor):
            raise ValidationError("Only an owner can create internal accounts.")
        return cleaned_data

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = user.email
        user.is_active = False
        user.is_active_staff_member = False
        user.email_verified_at = None
        user.can_use_pos = user.role == User.Role.CASHIER
        user.set_unusable_password()
        if commit:
            user.save()
        return user


class RejectCurrentPasswordMixin:
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("new_password1")
        if password and self.user.has_usable_password() and self.user.check_password(password):
            self.add_error(
                "new_password1",
                ValidationError("Your new password must be different from your current password."),
            )
        return cleaned_data


class ActivationSetPasswordForm(RejectCurrentPasswordMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(FORM_CONTROL)


class SecurePasswordChangeForm(RejectCurrentPasswordMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(FORM_CONTROL)


class EligiblePasswordResetForm(PasswordResetForm):
    email = forms.EmailField(
        max_length=254,
        widget=forms.EmailInput(attrs={**FORM_CONTROL, "autocomplete": "email"})
    )

    def clean_email(self):
        return User.objects.normalize_email(self.cleaned_data["email"])

    def get_users(self, email):
        users = User._default_manager.filter(
            email__iexact=email,
            email_verified_at__isnull=False,
            is_active=True,
            is_locked=False,
        )
        for user in users:
            if not user.has_usable_password():
                continue
            if user.role in {User.Role.OWNER, User.Role.CASHIER, User.Role.STAFF} and not user.is_active_staff_member:
                continue
            yield user


class HashedRecoveryCodeMixin:
    def clean_code(self):
        failure_key = f"accounts.mfa-failures.{self.user.pk}"
        if cache.add(failure_key, 1, settings.MFA_FAILURE_TIMEOUT):
            attempt_count = 1
        else:
            try:
                attempt_count = cache.incr(failure_key)
            except ValueError:
                cache.set(failure_key, 1, settings.MFA_FAILURE_TIMEOUT)
                attempt_count = 1

        if attempt_count > settings.MFA_FAILURE_LIMIT:
            self._record_mfa_failure(locked=True)
            raise ValidationError("Too many incorrect codes. Try again later.")

        code = self.cleaned_data["code"]
        try:
            normalized = MFARecoveryCode.normalize(code)
            if len(normalized) == 12:
                clear_rate_limit = check_rate_limit(self.user)
                if MFARecoveryCode.consume(self.user, code):
                    self.authenticator = Authenticator.objects.get(
                        user=self.user,
                        type=Authenticator.Type.TOTP,
                    )
                    from apps.audittrail.events import record_security_event
                    from apps.audittrail.models import SecurityEvent

                    record_security_event(
                        SecurityEvent.Action.MFA_RECOVERY_USED,
                        request=context.request,
                        user=self.user,
                        target=self.authenticator,
                    )
                    clear_rate_limit()
                    cache.delete(failure_key)
                    return code
            result = super().clean_code()
        except ValidationError:
            locked = attempt_count >= settings.MFA_FAILURE_LIMIT
            self._record_mfa_failure(locked=locked)
            if locked:
                raise ValidationError("Too many incorrect codes. Try again later.")
            raise
        cache.delete(failure_key)
        return result

    def _record_mfa_failure(self, *, locked):
        from apps.audittrail.events import record_security_event
        from apps.audittrail.models import SecurityEvent

        record_security_event(
            SecurityEvent.Action.MFA_LOCKED if locked else SecurityEvent.Action.MFA_FAILED,
            request=context.request,
            user=self.user,
            target=self.user,
            result=SecurityEvent.Result.FAILURE,
        )


class MFAAuthenticateForm(HashedRecoveryCodeMixin, AuthenticateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].max_length = 32
        self.fields["code"].widget.attrs.update({**FORM_CONTROL, "maxlength": "32"})


class MFAReauthenticateForm(HashedRecoveryCodeMixin, ReauthenticateForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["code"].max_length = 32
        self.fields["code"].widget.attrs.update({**FORM_CONTROL, "maxlength": "32"})


class MFAConfigurationForm(forms.ModelForm):
    class Meta:
        model = MFAConfiguration
        fields = ("require_internal_user_mfa",)
        labels = {
            "require_internal_user_mfa": "Require MFA for all CASHIER and STAFF accounts",
        }
        widgets = {
            "require_internal_user_mfa": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not self.actor or not is_owner(self.actor):
            raise ValidationError("Only an owner can change MFA requirements.")
        return cleaned_data


class RecoveryCodeRegenerationForm(forms.Form):
    confirm = forms.BooleanField(
        label="Invalidate all existing recovery codes and create new ones",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class LockoutClearForm(forms.Form):
    lockout = forms.CharField(max_length=1024, widget=forms.HiddenInput)
