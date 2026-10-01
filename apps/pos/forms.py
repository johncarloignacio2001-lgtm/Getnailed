from django import forms
from django.forms import BaseFormSet, formset_factory
from django.db.models import Q

from apps.accounts.models import User
from apps.bookings.models import Appointment
from apps.customers.models import Customer
from apps.services.models import Service

from .models import Payment, Sale


FORM_CONTROL = {"class": "form-control"}


class CheckoutForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=Customer.objects.none(),
        required=False,
        empty_label="Walk-in customer",
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    appointment = forms.ModelChoiceField(
        queryset=Appointment.objects.none(),
        required=False,
        empty_label="No linked appointment",
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    discount_type = forms.ChoiceField(
        choices=Sale.DiscountType.choices,
        initial=Sale.DiscountType.NONE,
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    discount_value = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01"}),
    )
    payment_method = forms.ChoiceField(
        choices=Payment.Method.choices,
        initial=Payment.Method.CASH,
        widget=forms.Select(attrs=FORM_CONTROL),
    )
    amount_tendered = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={**FORM_CONTROL, "step": "0.01", "inputmode": "decimal"}
        ),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs=FORM_CONTROL),
    )
    mark_appointment_completed = forms.BooleanField(
        required=False,
        initial=True,
        label="Mark linked appointment completed",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        visible_statuses = tuple(
            value
            for value, _ in Appointment.Status.choices
            if value not in (Appointment.Status.UNVERIFIED, Appointment.Status.EXPIRED)
        )
        self.fields["customer"].queryset = (
            Customer.objects.filter(
                Q(appointments__isnull=True)
                | Q(appointments__status__in=visible_statuses)
            )
            .distinct()
            .order_by("last_name", "first_name")
        )
        self.fields["appointment"].queryset = (
            Appointment.objects.exclude(
                status__in=(
                    Appointment.Status.UNVERIFIED,
                    Appointment.Status.REJECTED,
                    Appointment.Status.CANCELLED,
                    Appointment.Status.EXPIRED,
                )
            )
            .filter(sale__isnull=True)
            .select_related("customer")
            .order_by("appointment_date", "start_time")
        )
        


class CheckoutItemForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Service.objects.none(),
        widget=forms.Select(attrs={**FORM_CONTROL, "class": "form-select pos-service"}),
    )
    assigned_staff = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={**FORM_CONTROL, "class": "form-select"}),
    )
    quantity = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=1,
        widget=forms.NumberInput(
            attrs={**FORM_CONTROL, "min": "1", "max": "100", "inputmode": "numeric"}
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["service"].queryset = Service.objects.filter(
            is_active=True
        ).select_related("category")
        self.fields["assigned_staff"].queryset = User.objects.filter(
            role=User.Role.STAFF,
            is_active=True,
            is_active_staff_member=True,
            staff_profile__is_active=True,
        ).order_by("first_name", "last_name", "email")


class BaseCheckoutItemFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(form.cleaned_data and form.cleaned_data.get("service") for form in self.forms):
            raise forms.ValidationError("Add at least one service to the sale.")


CheckoutItemFormSet = formset_factory(
    CheckoutItemForm,
    formset=BaseCheckoutItemFormSet,
    extra=6,
    max_num=12,
    validate_max=True,
)


class SaleHistoryFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Receipt or customer"}),
    )
    date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"), *Sale.Status.choices),
        widget=forms.Select(attrs=FORM_CONTROL),
    )


class VoidSaleForm(forms.Form):
    reason = forms.CharField(
        min_length=3,
        max_length=500,
        widget=forms.Textarea(attrs={**FORM_CONTROL, "rows": 4}),
    )
