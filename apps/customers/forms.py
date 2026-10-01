from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Customer
from apps.accounts.models import User


class CustomerAccountForm(forms.Form):
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    phone = forms.CharField(required=False, max_length=30, widget=forms.TextInput(attrs={"class": "form-control"}))

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        if Customer.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered as a customer.")
        return email


class CustomerRegistrationForm(forms.Form):
    first_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "given-name"}),
    )
    last_name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "family-name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "autocomplete": "email"})
    )
    phone = forms.CharField(
        required=False,
        max_length=30,
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "tel"}),
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )
    password_confirmation = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "autocomplete": "new-password"}),
    )

    def clean_email(self):
        email = User.objects.normalize_email(self.cleaned_data["email"])
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("An account with this email already exists.")
        if Customer.objects.filter(email__iexact=email).exists():
            raise ValidationError("This email is already registered as a customer.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned_data = super().clean()
        if (
            cleaned_data.get("password")
            and cleaned_data.get("password_confirmation")
            and cleaned_data["password"] != cleaned_data["password_confirmation"]
        ):
            self.add_error("password_confirmation", "The passwords do not match.")
        return cleaned_data


FORM_CONTROL = {"class": "form-control"}


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("first_name", "last_name", "email", "phone", "notes")
        widgets = {
            "first_name": forms.TextInput(attrs=FORM_CONTROL),
            "last_name": forms.TextInput(attrs=FORM_CONTROL),
            "email": forms.EmailInput(attrs=FORM_CONTROL),
            "phone": forms.TextInput(attrs=FORM_CONTROL),
            "notes": forms.Textarea(attrs={**FORM_CONTROL, "rows": 4}),
        }

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
