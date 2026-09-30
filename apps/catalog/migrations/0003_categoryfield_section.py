"""Add CategoryField.section and group the two seeded categories' fields (staging already has them published)."""
from django.db import migrations, models

SECTIONS = {
    "water_abstraction": {
        "Licence and source": ["licence", "well", "source_type"],
        "Reporting period": ["period_start", "period_end"],
        "Volumes": ["abstraction_rate_m3_d", "abstraction_volume_m3", "meter_reading"],
        "Remarks": ["remarks"],
    },
    "water_quality": {
        "Sample": ["source_type", "well", "spring", "station", "sample_ref", "sample_depth_m"],
        "Dates and people": ["sampled_at", "analysed_at", "sampled_by", "analysed_by"],
        "Field measurements": ["specific_conductivity_us_cm", "temperature_c", "ph", "turbidity_ntu", "colour", "odour"],
        "Major ions": ["calcium_mg_l", "magnesium_mg_l", "potassium_mg_l", "sodium_mg_l", "carbonate_mg_l", "bicarbonate_mg_l", "sulphate_mg_l", "chloride_mg_l", "nitrate_mg_l"],
        "Derived and totals": ["hardness_mg_l", "alkalinity_mg_l", "total_dissolved_solids_mg_l", "percent_sodium", "sodium_adsorption_ratio"],
    },
}


def apply_sections(apps, schema_editor):
    """Set section and re-order fields so each section is contiguous on the form."""
    CategoryField = apps.get_model("catalog", "CategoryField")
    for code, sections in SECTIONS.items():
        order = 0
        for heading, names in sections.items():
            for name in names:
                order += 1
                CategoryField.objects.filter(version__category__code=code, name=name).update(section=heading, order=order)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0002_initial")]
    operations = [
        migrations.AddField(
            model_name="categoryfield",
            name="section",
            field=models.CharField(blank=True, help_text="Heading the field is grouped under on the entry form, e.g. 'Major ions'. Blank = 'Details'.", max_length=80),
        ),
        migrations.RunPython(apply_sections, migrations.RunPython.noop),
    ]
