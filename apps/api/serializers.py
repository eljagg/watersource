"""DRF serializers for the read-only data API and the submission endpoint (ToR F.7, H.xii)."""
from rest_framework import serializers

from apps.catalog.models import CategoryVersion, DataCategory
from apps.core.restrict import mask_site
from apps.lic.models import Licence, LicenceApplication
from apps.obs.models import AbstractionRecord, WaterQualitySample, WellWaterLevel
from apps.ref.models import Parish, StreamflowStation, Well
from apps.submissions.models import Submission, SubmissionRecord


class ParishSerializer(serializers.ModelSerializer):
    """Parish code and name."""
    class Meta:
        model = Parish
        fields = ["code", "name"]


class SiteMaskMixin:
    """Coarsen coordinates of public-supply sources for callers without a restricted-data role (ADR-0002)."""

    def to_representation(self, instance):
        """Serialise, then overwrite coordinate fields with the masked values."""
        data = super().to_representation(instance)
        request = self.context.get("request")
        user = getattr(request, "user", None)
        masked = mask_site(instance, user)
        for key in ("easting", "northing", "elevation_m"):
            if key in data:
                data[key] = None if masked[key] is None else f"{masked[key]:.3f}"
        data["coordinates_coarsened"] = masked["coordinates_coarsened"]
        return data


class WellSerializer(SiteMaskMixin, serializers.ModelSerializer):
    """Public well fields (no owner/personal data); coordinates coarsened for public-supply wells."""
    parish = serializers.SlugRelatedField(read_only=True, slug_field="name")
    basin = serializers.SlugRelatedField(read_only=True, slug_field="name")
    wmu = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = Well
        fields = ["id", "name", "aliases", "is_public_supply", "easting", "northing", "elevation_m", "parish", "basin", "wmu", "use",
                  "is_licensed", "is_abandoned", "is_index_well", "completion_date", "classification", "approval_state"]


class StationSerializer(SiteMaskMixin, serializers.ModelSerializer):
    """Streamflow station fields; coordinates coarsened for public-supply intakes."""
    parish = serializers.SlugRelatedField(read_only=True, slug_field="name")
    river = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = StreamflowStation
        fields = ["id", "name", "aliases", "river", "is_public_supply", "easting", "northing", "elevation_m", "parish", "is_active", "classification"]


class WellWaterLevelSerializer(serializers.ModelSerializer):
    """Well water level with grade and qualifiers."""
    well = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = WellWaterLevel
        fields = ["id", "well", "measured_at", "water_level_m", "well_state", "grade", "qualifiers", "classification"]


class AbstractionSerializer(serializers.ModelSerializer):
    """Abstraction record."""
    licence = serializers.SlugRelatedField(read_only=True, slug_field="number")
    well = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = AbstractionRecord
        fields = ["id", "licence", "well", "source_type", "period_start", "period_end", "abstraction_volume_m3",
                  "daily_volume_granted_m3", "over_limit", "over_limit_pct", "classification", "grade", "qualifiers"]


class WaterQualitySerializer(serializers.ModelSerializer):
    """Water-quality sample parameters."""
    well = serializers.SlugRelatedField(read_only=True, slug_field="name")
    station = serializers.SlugRelatedField(read_only=True, slug_field="name")
    spring = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = WaterQualitySample
        exclude = ["created_by", "updated_by", "laboratory", "extra", "paper_ref", "electronic_ref", "source"]


class LicenceSerializer(serializers.ModelSerializer):
    """Licence summary (staff only)."""
    licensee = serializers.SlugRelatedField(read_only=True, slug_field="name")
    parish = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = Licence
        fields = ["number", "licensee", "parish", "water_source", "source_name", "daily_volume_granted_m3", "issued_on", "expires_on", "status"]


class ApplicationSerializer(serializers.ModelSerializer):
    """Licence application summary (staff only)."""
    parish = serializers.SlugRelatedField(read_only=True, slug_field="name")

    class Meta:
        model = LicenceApplication
        fields = ["reference", "kind", "parish", "water_source", "source_name", "daily_volume_requested_m3", "daily_volume_granted_m3", "status", "submitted_at", "decided_at"]


class CategoryVersionSerializer(serializers.ModelSerializer):
    """Published category version with its fields and rules."""
    class Meta:
        model = CategoryVersion
        fields = ["version", "status", "published_at", "json_schema"]


class CategorySerializer(serializers.ModelSerializer):
    """Data category with its current version."""
    current_version = CategoryVersionSerializer(read_only=True)

    class Meta:
        model = DataCategory
        fields = ["code", "name", "description", "link_kind", "allow_csv", "allow_api", "current_version"]


class SubmissionRecordSerializer(serializers.ModelSerializer):
    """One row of a submission with validation outcome."""
    class Meta:
        model = SubmissionRecord
        fields = ["row_no", "status", "errors", "flags"]


class SubmissionSerializer(serializers.ModelSerializer):
    """Submission header and records."""
    category = serializers.CharField(source="category_version.category.code", read_only=True)
    version = serializers.IntegerField(source="category_version.version", read_only=True)
    records = SubmissionRecordSerializer(many=True, read_only=True)

    class Meta:
        model = Submission
        fields = ["id", "category", "version", "channel", "status", "row_count", "accepted_count", "flagged_count", "rejected_count", "classification", "created_at", "records"]


class SubmissionCreateSerializer(serializers.Serializer):
    """Payload for ``POST /api/v1/submissions/``: category code and rows."""
    category = serializers.SlugField()
    rows = serializers.ListField(child=serializers.DictField(), min_length=1, max_length=50000)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default="", max_length=64)
