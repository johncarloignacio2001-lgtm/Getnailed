from datetime import timedelta

from django import forms
from django.utils import timezone

from .models import ForecastRun


FORM_CONTROL = {"class": "form-control"}


class ForecastTrainingForm(forms.Form):
    start_date = forms.DateField(
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"})
    )
    end_date = forms.DateField(
        widget=forms.DateInput(attrs={**FORM_CONTROL, "type": "date"})
    )
    n_estimators = forms.IntegerField(
        min_value=50,
        max_value=1000,
        initial=200,
        label="Number of trees",
        widget=forms.NumberInput(attrs=FORM_CONTROL),
    )
    max_depth = forms.IntegerField(
        min_value=2,
        max_value=100,
        required=False,
        help_text="Leave blank to grow trees until other stopping rules apply.",
        widget=forms.NumberInput(attrs=FORM_CONTROL),
    )
    min_samples_leaf = forms.IntegerField(
        min_value=1,
        max_value=100,
        initial=1,
        widget=forms.NumberInput(attrs=FORM_CONTROL),
    )

    def __init__(self, *args, **kwargs):
        end = timezone.localdate() - timedelta(days=1)
        kwargs.setdefault(
            "initial", {"start_date": end - timedelta(days=364), "end_date": end}
        )
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        start = cleaned_data.get("start_date")
        end = cleaned_data.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("End date must be on or after start date.")
        if start and end and (end - start).days > 3660:
            raise forms.ValidationError("Training range cannot exceed ten years.")
        return cleaned_data


class ForecastGenerationForm(forms.Form):
    horizon_days = forms.IntegerField(
        min_value=1,
        max_value=365,
        initial=14,
        label="Forecast horizon (days)",
        widget=forms.NumberInput(attrs=FORM_CONTROL),
    )


class ForecastComparisonForm(forms.Form):
    runs = forms.ModelMultipleChoiceField(
        queryset=ForecastRun.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        help_text="Select two to five successfully trained runs.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["runs"].queryset = ForecastRun.objects.filter(
            status=ForecastRun.Status.TRAINED
        )

    def clean_runs(self):
        runs = self.cleaned_data["runs"]
        if not 2 <= len(runs) <= 5:
            raise forms.ValidationError("Select between two and five trained runs.")
        return runs
