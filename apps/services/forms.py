from django import forms
from django.db.models import Q

from apps.accounts.authorization import is_owner
from apps.accounts.models import User

from .models import Service, ServiceCategory, StaffProfile


FORM_CONTROL = {"class": "form-control"}


class OwnerManagedFormMixin:
    def __init__(self, *args, actor=None, **kwargs):
        self.actor = actor
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not self.actor or not is_owner(self.actor):
            raise forms.ValidationError("Only an owner can manage service records.")
        return cleaned_data


class ServiceCategoryForm(OwnerManagedFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceCategory
        fields = ("name", "description")
        widgets = {
            "name": forms.TextInput(attrs=FORM_CONTROL),
            "description": forms.Textarea(attrs={**FORM_CONTROL, "rows": 3}),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class ServiceForm(OwnerManagedFormMixin, forms.ModelForm):
    class Meta:
        model = Service
        fields = (
            "name",
            "category",
            "description",
            "duration_minutes",
            "price",
            "is_active",
            "image",
        )
        widgets = {
            "name": forms.TextInput(attrs=FORM_CONTROL),
            "category": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={**FORM_CONTROL, "rows": 5}),
            "duration_minutes": forms.NumberInput(
                attrs={**FORM_CONTROL, "min": "5", "max": "480", "step": "5"}
            ),
            "price": forms.NumberInput(
                attrs={**FORM_CONTROL, "min": "0.01", "step": "0.01"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "image": forms.ClearableFileInput(
                attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}
            ),
        }

    def clean_name(self):
        return " ".join(self.cleaned_data["name"].split())


class StaffProfileForm(OwnerManagedFormMixin, forms.ModelForm):
    class Meta:
        model = StaffProfile
        fields = ("user", "specialty", "availability_status", "is_active")
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "specialty": forms.TextInput(attrs=FORM_CONTROL),
            "availability_status": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        profile_user_id = self.instance.user_id if self.instance and self.instance.pk else None
        self.fields["user"].queryset = User.objects.filter(role=User.Role.STAFF).filter(
            Q(staff_profile__isnull=True) | Q(pk=profile_user_id)
        ).order_by("first_name", "last_name", "email")

    def clean_specialty(self):
        return " ".join(self.cleaned_data["specialty"].split())


class ServiceFilterForm(forms.Form):
    q = forms.CharField(max_length=100, required=False)
    category = forms.ModelChoiceField(
        queryset=ServiceCategory.objects.none(),
        required=False,
        empty_label="All categories",
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"), ("active", "Active"), ("inactive", "Inactive")),
    )

    def __init__(self, *args, include_inactive=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = ServiceCategory.objects.order_by("name")
        if not include_inactive:
            self.fields["status"].choices = (("active", "Active services"),)
            self.fields["status"].initial = "active"
        for field in self.fields.values():
            field.widget.attrs.update(
                {"class": "form-select" if isinstance(field.widget, forms.Select) else "form-control"}
            )


class StaffProfileFilterForm(forms.Form):
    q = forms.CharField(max_length=100, required=False)
    availability = forms.ChoiceField(
        required=False,
        choices=(("", "All availability"), *StaffProfile.Availability.choices),
    )
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"), ("active", "Active"), ("inactive", "Inactive")),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update(
                {"class": "form-select" if isinstance(field.widget, forms.Select) else "form-control"}
            )
