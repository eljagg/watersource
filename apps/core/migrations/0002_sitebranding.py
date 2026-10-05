"""Site branding singleton (logo, names, tagline) editable in the admin console."""
from django.db import migrations, models


class Migration(migrations.Migration):
    """Add ``SiteBranding``."""

    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="SiteBranding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("organisation_name", models.CharField(default="Water Resources Authority of Jamaica", help_text="Shown in the footer and on the wall display.", max_length=120, verbose_name="Organisation name")),
                ("product_name", models.CharField(default="WaterSource", help_text="Shown next to the logo and in the browser tab.", max_length=40, verbose_name="Application name")),
                ("tagline", models.CharField(blank=True, default="Jamaica · WRA", help_text="Small line under the application name in the header.", max_length=80, verbose_name="Tagline")),
                ("footer_text", models.CharField(blank=True, default="", help_text="Optional. Leave empty to show the organisation name.", max_length=200, verbose_name="Footer line")),
                ("logo", models.BinaryField(blank=True, editable=False, null=True, verbose_name="Logo")),
                ("logo_type", models.CharField(blank=True, default="", editable=False, max_length=20)),
                ("logo_dark", models.BinaryField(blank=True, editable=False, null=True, verbose_name="Logo for dark backgrounds")),
                ("logo_dark_type", models.CharField(blank=True, default="", editable=False, max_length=20)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"verbose_name": "site branding", "verbose_name_plural": "site branding"},
        ),
    ]
