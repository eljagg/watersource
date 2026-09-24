from django import forms

from apps.core.uploads import validate_upload

from .models import ApplicationDocument, LicenceApplication


class ApplicationForm(forms.ModelForm):
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
        self.fields["renewal_of"].required = False
        if user is not None and user.is_client:
            self.fields["renewal_of"].queryset = self.fields["renewal_of"].queryset.filter(licensee__accounts=user)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("water_source") == "well" and not cleaned.get("well") and not cleaned.get("source_name"):
            self.add_error("source_name", "Give the well name if it is not yet registered.")
        return cleaned


class DocumentForm(forms.ModelForm):
    class Meta:
        model = ApplicationDocument
        fields = ["kind", "file"]

    def clean_file(self):
        f = self.cleaned_data["file"]
        self.detected_type = validate_upload(f)
        return f
