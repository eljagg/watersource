"""Forms for the licence application and document upload (ToR item 14)."""
from django import forms

from apps.core.uploads import validate_upload

from .models import ApplicationDocument, LicenceApplication, LicenceCondition, TechnicalAssessment


class ApplicationForm(forms.ModelForm):
    """Applicant-facing application form; pre-fills contact fields from the user."""
    class Meta:
        model = LicenceApplication
        fields = ["kind", "applicant_name", "applicant_address", "applicant_email", "applicant_phone", "parish",
                  "water_source", "source_name", "well", "daily_volume_requested_m3", "purpose", "renewal_of"]
        widgets = {"applicant_address": forms.Textarea(attrs={"rows": 3}), "purpose": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        if user is not None and not self.instance.pk:
            self.fields["applicant_name"].initial = user.full_name
            self.fields["applicant_email"].initial = user.email
            self.fields["applicant_phone"].initial = user.phone
        self.fields["well"].required = False
        self.fields["daily_volume_requested_m3"].label = "Daily volume requested (m³/day)"
        self.fields["kind"].label = "Type of application"
        self.fields["renewal_of"].required = False
        if user is not None and user.is_client:
            self.fields["renewal_of"].queryset = self.fields["renewal_of"].queryset.filter(licensee__accounts=user)

    def clean(self):
        """Require a well for groundwater sources."""
        cleaned = super().clean()
        if cleaned.get("water_source") == "well" and not cleaned.get("well") and not cleaned.get("source_name"):
            self.add_error("source_name", "Give the well name if it is not yet registered.")
        return cleaned


class DocumentForm(forms.ModelForm):
    """Supporting document upload with type/size validation."""
    class Meta:
        model = ApplicationDocument
        fields = ["kind", "file"]

    def clean_file(self):
        """Validate the upload and remember the detected MIME type."""
        f = self.cleaned_data["file"]
        self.detected_type = validate_upload(f)
        return f


class TechnicalAssessmentForm(forms.ModelForm):
    """Hydrologist's assessment (design doc 14 §4): WMU, aquifer, impact, recommendation, conditions."""

    class Meta:
        model = TechnicalAssessment
        fields = ["wmu", "aquifer", "impact", "recommendation", "recommended_daily_volume_m3", "conditions", "extra_conditions", "findings"]
        widgets = {"findings": forms.Textarea(attrs={"rows": 5}), "extra_conditions": forms.Textarea(attrs={"rows": 3}), "conditions": forms.CheckboxSelectMultiple()}

    def __init__(self, *args, application=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.application = application
        qs = LicenceCondition.objects.filter(is_active=True)
        if application is not None:
            qs = qs.filter(applies_to__in=["both", application.water_source])
            if not self.instance.pk:
                self.fields["conditions"].initial = list(qs.filter(is_default=True).values_list("pk", flat=True))
                self.fields["recommended_daily_volume_m3"].initial = application.daily_volume_requested_m3
                if application.well_id and application.well.wmu_id:
                    self.fields["wmu"].initial = application.well.wmu_id
                if application.well_id and application.well.aquifer_id:
                    self.fields["aquifer"].initial = application.well.aquifer_id
        self.fields["conditions"].queryset = qs
        self.fields["conditions"].label = "Standard conditions"
        self.fields["conditions"].label_from_instance = lambda c: f"{c.title} ({c.get_category_display().lower()})"
        self.fields["wmu"].label = "Watershed management unit"
        for name in ("wmu", "aquifer", "impact", "recommendation", "recommended_daily_volume_m3"):
            self.fields[name].wide = False
        self.fields["findings"].wide = self.fields["extra_conditions"].wide = self.fields["conditions"].wide = True

    def clean(self):
        """A reduced grant needs a volume; refusal needs findings."""
        cleaned = super().clean()
        if cleaned.get("recommendation") == "grant_reduced" and not cleaned.get("recommended_daily_volume_m3"):
            self.add_error("recommended_daily_volume_m3", "Give the reduced daily volume you recommend.")
        return cleaned
