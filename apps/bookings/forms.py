import re
from datetime import datetime

from django import forms
from django.utils import timezone

from apps.accounts.models import User
from apps.services.models import Service, StaffProfile

from .models import Appointment, Booking
from .services import MANAGER_TRANSITIONS, STAFF_TRANSITIONS


FORM_CONTROL = {"class": "form-control"}
BOOKING_REFERENCE_RE = re.compile(r"^(?:BK-[A-Za-z0-9_-]{1,29}|\d{6,32})$", re.IGNORECASE)
BOOKING_ACCESS_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PublicBookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = (
            "customer_name",
            "email",
            "phone_number",
            "service_name",
            "scheduled_for",
        )
        widgets = {
            "customer_name": forms.TextInput(attrs=FORM_CONTROL),
            "email": forms.EmailInput(attrs={**FORM_CONTROL, "autocomplete": "email"}),
            "phone_number": forms.TextInput(attrs=FORM_CONTROL),
            "service_name": forms.TextInput(attrs=FORM_CONTROL),
            "scheduled_for": forms.DateTimeInput(
                attrs={**FORM_CONTROL, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()

    def clean_scheduled_for(self):
        scheduled_for = self.cleaned_data["scheduled_for"]
        if scheduled_for <= timezone.now():
            raise forms.ValidationError("Choose a future appointment time.")
        return scheduled_for


class PublicContactForm(forms.Form):
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FORM_CONTROL))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs=FORM_CONTROL))
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={**FORM_CONTROL, "autocomplete": "email"})
    )
    phone = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "autocomplete": "tel"}),
    )
    notes = forms.CharField(
        required=False,
        max_length=2000,
        widget=forms.Textarea(attrs={**FORM_CONTROL, "rows": 3}),
    )

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class PublicServiceForm(forms.Form):
    services = forms.ModelMultipleChoiceField(
        queryset=Service.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        error_messages={"required": "Choose at least one service."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["services"].queryset = Service.objects.filter(is_active=True).select_related(
            "category"
        )


class PublicScheduleForm(forms.Form):
    appointment_date = forms.DateField(
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"})
    )
    start_time = forms.TimeField(
        widget=forms.TimeInput(attrs={**FORM_CONTROL, "type": "time"})
    )
    assigned_staff = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="No preference",
        widget=forms.Select(attrs=FORM_CONTROL),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_staff"].queryset = User.objects.filter(
            role=User.Role.STAFF,
            is_active=True,
            is_active_staff_member=True,
            staff_profile__is_active=True,
            staff_profile__availability_status=StaffProfile.Availability.AVAILABLE,
        ).order_by("first_name", "last_name", "email")

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get("appointment_date")
        start_time = cleaned_data.get("start_time")
        if appointment_date and start_time:
            scheduled_for = timezone.make_aware(
                datetime.combine(appointment_date, start_time),
                timezone.get_current_timezone(),
            )
            if scheduled_for <= timezone.now():
                raise forms.ValidationError("Choose a future appointment time.")
        return cleaned_data


class AppointmentFilterForm(forms.Form):
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"), *Appointment.Status.choices),
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    staff = forms.ModelChoiceField(
        required=False,
        queryset=User.objects.filter(role=User.Role.STAFF),
        empty_label="All staff",
        widget=forms.Select(attrs=FORM_CONTROL),
    )


class AppointmentStatusForm(forms.Form):
    status = forms.ChoiceField(widget=forms.Select(attrs=FORM_CONTROL))
    note = forms.CharField(
        required=False,
        max_length=500,
        widget=forms.Textarea(attrs={**FORM_CONTROL, "rows": 2}),
    )

    def __init__(self, *args, appointment, actor, **kwargs):
        super().__init__(*args, **kwargs)
        transitions = (
            STAFF_TRANSITIONS
            if actor.is_service_staff and not actor.is_owner
            else MANAGER_TRANSITIONS
        )
        allowed = transitions.get(appointment.status, set())
        self.fields["status"].choices = [
            choice for choice in Appointment.Status.choices if choice[0] in allowed
        ]


class AppointmentScheduleForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = ("appointment_date", "start_time", "assigned_staff")
        widgets = {
            "appointment_date": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "start_time": forms.TimeInput(attrs={**FORM_CONTROL, "type": "time"}),
            "assigned_staff": forms.Select(attrs=FORM_CONTROL),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assigned_staff"].queryset = User.objects.filter(
            role=User.Role.STAFF,
            is_active=True,
            is_active_staff_member=True,
            staff_profile__is_active=True,
            staff_profile__availability_status=StaffProfile.Availability.AVAILABLE,
        ).order_by("first_name", "last_name", "email")

    def clean(self):
        cleaned_data = super().clean()
        appointment_date = cleaned_data.get("appointment_date")
        start_time = cleaned_data.get("start_time")
        if appointment_date and start_time:
            value = timezone.make_aware(
                datetime.combine(appointment_date, start_time),
                timezone.get_current_timezone(),
            )
            if value <= timezone.now():
                raise forms.ValidationError("Choose a future appointment time.")
        return cleaned_data


class BookingVerificationForm(forms.Form):
    reference = forms.RegexField(
        BOOKING_REFERENCE_RE,
        max_length=32,
        error_messages={"invalid": "Enter a valid booking reference."},
        widget=forms.TextInput(attrs=FORM_CONTROL),
    )
    code = forms.RegexField(
        r"^\d{8}$",
        error_messages={"invalid": "Enter the eight-digit verification code."},
        widget=forms.TextInput(
            attrs={
                **FORM_CONTROL,
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "maxlength": "8",
            }
        ),
    )


class BookingResendForm(forms.Form):
    reference = forms.RegexField(
        BOOKING_REFERENCE_RE,
        max_length=32,
        error_messages={"invalid": "Enter a valid booking reference."},
        widget=forms.TextInput(attrs=FORM_CONTROL),
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs=FORM_CONTROL))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class BookingLookupForm(forms.Form):
    reference = forms.RegexField(
        BOOKING_REFERENCE_RE,
        max_length=32,
        error_messages={"invalid": "Enter a valid booking reference."},
        widget=forms.TextInput(attrs=FORM_CONTROL),
    )
    access_token = forms.RegexField(
        BOOKING_ACCESS_TOKEN_RE,
        max_length=64,
        error_messages={"invalid": "Enter a valid booking access token."},
        widget=forms.TextInput(attrs=FORM_CONTROL),
    )


class BookingRescheduleForm(forms.Form):
    scheduled_for = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={**FORM_CONTROL, "type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
        input_formats=("%Y-%m-%dT%H:%M",),
    )

    def clean_scheduled_for(self):
        scheduled_for = self.cleaned_data["scheduled_for"]
        if scheduled_for <= timezone.now():
            raise forms.ValidationError("Choose a future appointment time.")
        return scheduled_for


class BookingCancellationForm(forms.Form):
    confirm = forms.BooleanField(label="Cancel this booking")
