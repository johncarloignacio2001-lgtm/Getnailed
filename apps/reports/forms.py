from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.accounts.models import User


FORM_CONTROL = {"class": "form-control"}


class ReportDateRangeForm(forms.Form):
    PRESET_CHOICES = (
        ("custom", "Custom Range"),
        ("day", "Today (Day)"),
        ("week", "This Week"),
        ("month", "This Month"),
        ("year", "This Year"),
    )
    preset = forms.ChoiceField(
        choices=PRESET_CHOICES,
        required=False,
        initial="custom",
        widget=forms.Select(attrs={**FORM_CONTROL, "id": "preset-select"}),
    )
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"})
    )

    def __init__(self, *args, report_type, **kwargs):
        today = timezone.localdate()
        defaults = {
            "daily": (today, today),
            "weekly": (today - timedelta(days=6), today),
            "monthly": (today.replace(day=1), today),
            "annual": (today.replace(month=1, day=1), today),
            "service-sales": (today.replace(day=1), today),
            "appointment-status": (today.replace(day=1), today),
            "staff-workload": (today.replace(day=1), today),
            "top-services": (today.replace(day=1), today),
            "top-staff": (today.replace(day=1), today),
        }
        kwargs.setdefault(
            "initial",
            {
                "preset": "custom",
                "start_date": defaults.get(report_type, (today.replace(day=1), today))[0],
                "end_date": defaults.get(report_type, (today.replace(day=1), today))[1],
            },
        )
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        preset = cleaned_data.get("preset")
        today = timezone.localdate()
        if preset == "day":
            cleaned_data["start_date"] = today
            cleaned_data["end_date"] = today
        elif preset == "week":
            cleaned_data["start_date"] = today - timedelta(days=6)
            cleaned_data["end_date"] = today
        elif preset == "month":
            cleaned_data["start_date"] = today.replace(day=1)
            cleaned_data["end_date"] = today
        elif preset == "year":
            cleaned_data["start_date"] = today.replace(month=1, day=1)
            cleaned_data["end_date"] = today

        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after start date.")
        if start and end and (end - start).days > 3660:
            raise forms.ValidationError("Choose a date range of ten years or less.")
        return cleaned_data


class DailySummaryForm(forms.Form):
    date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"}),
    )
    cashier = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="All cashiers",
        widget=forms.Select(attrs=FORM_CONTROL),
    )

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cashier"].queryset = User.objects.filter(
            processed_sales__isnull=False
        ).distinct()
        if not actor.is_owner:
            self.fields.pop("cashier")
