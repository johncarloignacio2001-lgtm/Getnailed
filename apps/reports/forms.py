from datetime import timedelta

from django import forms
from django.utils import timezone

from apps.accounts.models import User


FORM_CONTROL = {"class": "form-control"}


class ReportDateRangeForm(forms.Form):
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
        }
        kwargs.setdefault(
            "initial",
            {"start_date": defaults[report_type][0], "end_date": defaults[report_type][1]},
        )
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
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
