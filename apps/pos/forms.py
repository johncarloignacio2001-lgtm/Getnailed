from django import forms
from django.forms import BaseFormSet, formset_factory
from django.db.models import Q

from apps.accounts.models import User
from apps.bookings.models import Appointment
from apps.customers.models import Customer
from apps.services.models import Service

from .models import CashierShift, Payment, PromoVoucher, Sale


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
        widget=forms.Select(attrs={**FORM_CONTROL, "id": "id_discount_type"}),
    )
    discount_value = forms.DecimalField(
        min_value=0,
        max_digits=12,
        decimal_places=2,
        initial=0,
        required=False,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01", "id": "id_discount_value"}),
    )
    discount_id_number = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Senior / PWD ID Number", "id": "id_discount_id_number"}),
    )
    discount_id_name = forms.CharField(
        required=False,
        max_length=160,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Cardholder full name", "id": "id_discount_id_name"}),
    )
    voucher_code = forms.CharField(
        required=False,
        max_length=50,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Voucher Code", "id": "id_voucher_code"}),
    )
    max_discount_cap = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01", "placeholder": "Discount cap in ₱ (optional)", "id": "id_max_discount_cap"}),
    )
    payment_method = forms.ChoiceField(
        choices=(
            (Payment.Method.CASH, "Cash"),
            (Payment.Method.GCASH, "GCash"),
            (Payment.Method.MAYA, "Maya"),
        ),
        initial=Payment.Method.CASH,
        widget=forms.Select(attrs={**FORM_CONTROL, "id": "id_payment_method"}),
    )
    amount_tendered = forms.DecimalField(
        required=False,
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(
            attrs={**FORM_CONTROL, "step": "0.01", "inputmode": "decimal", "id": "id_amount_tendered"}
        ),
    )
    payment_reference = forms.CharField(
        required=False,
        max_length=100,
        widget=forms.TextInput(attrs={**FORM_CONTROL, "placeholder": "Reference number (for GCash / Maya)", "id": "id_payment_reference"}),
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
        self.fields["appointment"].label_from_instance = lambda obj: (
            f"Ref #{obj.booking_reference} - {obj.customer_name_snapshot} ({obj.appointment_date} {obj.start_time.strftime('%I:%M %p')})"
        )

    def clean(self):
        cleaned_data = super().clean()
        dtype = cleaned_data.get("discount_type")
        id_num = cleaned_data.get("discount_id_number", "").strip()
        vcode = cleaned_data.get("voucher_code", "").strip()

        if dtype in (Sale.DiscountType.SENIOR_CITIZEN, Sale.DiscountType.PWD):
            if not id_num:
                self.add_error("discount_id_number", "ID number is mandatory for Senior Citizen and PWD discounts.")
        elif dtype == Sale.DiscountType.PROMO_VOUCHER:
            if not vcode:
                self.add_error("voucher_code", "Please enter a promo voucher code.")
            else:
                voucher = PromoVoucher.objects.filter(code=vcode.upper(), is_active=True).first()
                if not voucher:
                    self.add_error("voucher_code", "Voucher code not found or inactive.")
                else:
                    cleaned_data["voucher_obj"] = voucher
        return cleaned_data


class CheckoutItemForm(forms.Form):
    service = forms.ModelChoiceField(
        queryset=Service.objects.none(),
        required=False,
        empty_label="-- Select Service --",
        widget=forms.Select(attrs={**FORM_CONTROL, "class": "form-select pos-service"}),
    )
    assigned_staff = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Unassigned",
        widget=forms.Select(attrs={**FORM_CONTROL, "class": "form-select pos-staff"}),
    )
    service_time = forms.TimeField(
        required=False,
        input_formats=["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"],
        widget=forms.TimeInput(
            attrs={**FORM_CONTROL, "type": "time", "class": "form-control pos-time"}
        ),
    )
    quantity = forms.IntegerField(
        required=False,
        initial=1,
        widget=forms.HiddenInput(attrs={"value": "1"}),
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
        ).select_related("staff_profile").order_by("first_name", "last_name", "email")
        self.fields["assigned_staff"].label_from_instance = (
            lambda u: f"{u.get_full_name()} — {u.staff_profile.specialty}"
            if getattr(u, "staff_profile", None) and u.staff_profile.specialty
            else u.get_full_name() or u.email
        )

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("quantity"):
            cleaned_data["quantity"] = 1
        return cleaned_data


class BaseCheckoutItemFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        if not any(
            form.cleaned_data and form.cleaned_data.get("service")
            for form in self.forms
        ):
            raise forms.ValidationError("Add at least one service to the sale.")


CheckoutItemFormSet = formset_factory(
    CheckoutItemForm,
    formset=BaseCheckoutItemFormSet,
    extra=6,
    max_num=12,
    validate_max=True,
)


class OpenShiftForm(forms.Form):
    opening_cash = forms.DecimalField(
        label="Opening Cash Float (₱)",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        initial=0,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01", "placeholder": "e.g., 2000.00"}),
        help_text="Starting cash amount in the cash drawer.",
    )
    notes = forms.CharField(
        label="Shift Notes",
        required=False,
        widget=forms.Textarea(attrs={**FORM_CONTROL, "rows": 2, "placeholder": "Optional opening notes"}),
    )


class CloseShiftForm(forms.Form):
    closing_cash = forms.DecimalField(
        label="Actual Cash in Drawer (₱)",
        min_value=0,
        max_digits=12,
        decimal_places=2,
        widget=forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01", "placeholder": "Count physical cash and enter total"}),
        help_text="Physically counted cash in the till drawer at shift close.",
    )
    notes = forms.CharField(
        label="Closing Notes / Reconciliation Remarks",
        required=False,
        widget=forms.Textarea(attrs={**FORM_CONTROL, "rows": 3, "placeholder": "Explain any cash overage, shortage, or till notes"}),
    )


class PromoVoucherForm(forms.ModelForm):
    class Meta:
        model = PromoVoucher
        fields = (
            "code",
            "description",
            "discount_type",
            "discount_value",
            "max_discount_cap",
            "min_spend",
            "valid_from",
            "valid_until",
            "usage_limit",
            "is_active",
        )
        widgets = {
            "code": forms.TextInput(attrs=FORM_CONTROL),
            "description": forms.TextInput(attrs=FORM_CONTROL),
            "discount_type": forms.Select(attrs={"class": "form-select"}),
            "discount_value": forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01"}),
            "max_discount_cap": forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01"}),
            "min_spend": forms.NumberInput(attrs={**FORM_CONTROL, "step": "0.01"}),
            "valid_from": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "valid_until": forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
            "usage_limit": forms.NumberInput(attrs=FORM_CONTROL),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


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

