"""REST API v1 (ToR F.7, H.xii): read-only classified data, categories, submissions."""
from django.shortcuts import get_object_or_404
from rest_framework import mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.catalog.models import DataCategory
from apps.catalog.services import csv_template
from apps.lic.models import Licence, LicenceApplication
from apps.obs.models import AbstractionRecord, WaterQualitySample, WellWaterLevel
from apps.ref.models import Parish, StreamflowStation, Well
from apps.submissions import services as submission_services
from apps.submissions.models import Submission

from . import serializers
from .authentication import has_scope


class ClassifiedReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    """Guests see public rows; staff see approved rows; reviewers+ see all (ToR F.5)."""

    permission_classes = [permissions.AllowAny]
    filterset_fields: list = []

    def get_queryset(self):
        """Rows visible to the caller (public for guests, approved for staff, all for reviewers)."""
        return self.queryset.visible_to(self.request.user if self.request.user.is_authenticated else None)


class WellViewSet(ClassifiedReadOnlyViewSet):
    """Wells."""
    queryset = Well.objects.select_related("parish", "basin", "wmu")
    serializer_class = serializers.WellSerializer
    filterset_fields = ["parish", "basin", "wmu", "use", "is_licensed", "is_abandoned"]
    search_fields = ["name", "aliases"]


class StationViewSet(ClassifiedReadOnlyViewSet):
    """Streamflow stations."""
    queryset = StreamflowStation.objects.select_related("parish", "river")
    serializer_class = serializers.StationSerializer
    filterset_fields = ["parish", "river", "is_active"]


class WellWaterLevelViewSet(ClassifiedReadOnlyViewSet):
    """Well water levels."""
    queryset = WellWaterLevel.objects.select_related("well")
    serializer_class = serializers.WellWaterLevelSerializer
    filterset_fields = {"well": ["exact"], "measured_at": ["gte", "lte"]}


class AbstractionViewSet(ClassifiedReadOnlyViewSet):
    """Abstraction records."""
    queryset = AbstractionRecord.objects.select_related("licence", "well")
    serializer_class = serializers.AbstractionSerializer
    filterset_fields = {"licence": ["exact"], "well": ["exact"], "over_limit": ["exact"], "period_start": ["gte", "lte"]}


class WaterQualityViewSet(ClassifiedReadOnlyViewSet):
    """Water-quality samples."""
    queryset = WaterQualitySample.objects.select_related("well", "station", "spring")
    serializer_class = serializers.WaterQualitySerializer
    filterset_fields = {"well": ["exact"], "station": ["exact"], "source_type": ["exact"], "sampled_at": ["gte", "lte"]}


class ParishViewSet(viewsets.ReadOnlyModelViewSet):
    """Parishes (always public)."""
    queryset = Parish.objects.all()
    serializer_class = serializers.ParishSerializer
    permission_classes = [permissions.AllowAny]


class StaffOnly(permissions.BasePermission):
    """Permission: WRA staff or superuser."""
    def has_permission(self, request, view):
        """True for staff users."""
        u = request.user
        return u.is_authenticated and (u.is_staff_user or u.is_superuser)


class LicenceViewSet(viewsets.ReadOnlyModelViewSet):
    """Licence records for Finance & Accounts and internal reporting (ToR H.xiii). Staff only."""

    queryset = Licence.objects.select_related("licensee", "parish")
    serializer_class = serializers.LicenceSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ["status", "parish", "water_source"]


class ApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    """Licence applications (staff only)."""
    queryset = LicenceApplication.objects.select_related("parish")
    serializer_class = serializers.ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status", "parish", "water_source"]
    lookup_field = "reference"

    def get_queryset(self):
        """All applications, newest first."""
        u = self.request.user
        if getattr(self, "swagger_fake_view", False) or not u.is_authenticated:
            return self.queryset.none()
        return self.queryset if (u.is_staff_user or u.is_superuser) else self.queryset.filter(applicant_user=u)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Data categories with their current JSON Schema (ToR G.2.i, F.7.iv)."""

    queryset = DataCategory.objects.filter(is_active=True)
    serializer_class = serializers.CategorySerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = "code"

    @action(detail=True, methods=["get"], url_path="template.csv")
    def template(self, request, code=None):
        """Download the CSV template for a category."""
        from django.http import HttpResponse

        cat = self.get_object()
        return HttpResponse(csv_template(cat.current_version), content_type="text/csv")


class SubmissionViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Create and read data submissions over the API (``submissions:write`` scope)."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SubmissionSerializer
    queryset = Submission.objects.none()

    def get_queryset(self):
        """Own submissions for clients; all for staff."""
        qs = Submission.objects.select_related("category_version__category").prefetch_related("records")
        u = self.request.user
        if getattr(self, "swagger_fake_view", False) or not u.is_authenticated:
            return qs.none()
        return qs if (u.is_staff_user or u.is_superuser) else qs.filter(submitter=u)

    def create(self, request, *args, **kwargs):
        """Validate rows against the category and start the review workflow."""
        if not has_scope(request, "submissions:write"):
            return Response({"detail": "API key lacks scope submissions:write."}, status=status.HTTP_403_FORBIDDEN)
        ser = serializers.SubmissionCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cat = get_object_or_404(DataCategory, code=ser.validated_data["category"], is_active=True, allow_api=True)
        version = cat.current_version
        if version is None:
            return Response({"detail": "Category has no published version."}, status=status.HTTP_400_BAD_REQUEST)
        sub = submission_services.create_submission(
            version, ser.validated_data["rows"], request.user, channel="api", note=ser.validated_data["note"],
            idempotency_key=ser.validated_data["idempotency_key"],
        )
        out = serializers.SubmissionSerializer(sub)
        code = status.HTTP_202_ACCEPTED if sub.status == "under_review" else status.HTTP_422_UNPROCESSABLE_ENTITY
        return Response(out.data, status=code)


# ---------------------------------------------------------------------------
# Finance & Accounts export endpoints (ToR H.xiii) — JSON by default, ?download=csv for a file
# ---------------------------------------------------------------------------
class FinanceOnly(permissions.BasePermission):
    """Permission: ``finance`` or ``administrator`` role (API keys inherit their owner's roles)."""

    def has_permission(self, request, view):
        """True for finance/administrator users and superusers."""
        from apps.accounts import roles

        u = request.user
        return u.is_authenticated and (u.is_superuser or u.has_role(*roles.FINANCE_EXPORT_ROLES))


def _finance_response(request, name: str, columns: list[str], rows) -> Response:
    """Rows as a JSON list of objects, or as CSV when ``?download=csv``."""
    import csv

    from django.http import HttpResponse

    from apps.core import audit

    rows = list(rows)
    audit.log(f"export.finance_{name}", None, actor=request.user, summary=f"api · {len(rows)} rows")
    if request.query_params.get("download") == "csv":
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        w = csv.writer(resp)
        w.writerow(columns)
        w.writerows(rows)
        return resp
    return Response({"count": len(rows), "columns": columns, "results": [dict(zip(columns, r, strict=True)) for r in rows]})


class FinanceExportViewSet(viewsets.ViewSet):
    """Licence register and abstraction returns for Finance's fee system (``finance`` role or administrator)."""

    permission_classes = [FinanceOnly]
    serializer_class = serializers.FinanceRowSerializer  # documentation only; rows are plain dicts

    @action(detail=False, methods=["get"], url_path="licences")
    def licences(self, request):
        """Active licences (``?status=expired`` etc. for other states)."""
        from apps.integrations import exports

        return _finance_response(request, "licences", exports.FINANCE_LICENCE_COLUMNS, exports.finance_licence_rows(request.query_params.get("status") or None))

    @action(detail=False, methods=["get"], url_path="abstraction")
    def abstraction(self, request):
        """Approved abstraction returns in ``?from=YYYY-MM-DD&to=YYYY-MM-DD`` (default: current month to date)."""
        from datetime import datetime, time

        from django.utils import timezone
        from django.utils.dateparse import parse_date

        from apps.integrations import exports

        today = timezone.localdate()
        start = parse_date(request.query_params.get("from", "")) or today.replace(day=1)
        end = parse_date(request.query_params.get("to", "")) or today
        tz = timezone.get_current_timezone()
        s, e = timezone.make_aware(datetime.combine(start, time.min), tz), timezone.make_aware(datetime.combine(end, time.max), tz)
        return _finance_response(request, "abstraction", exports.FINANCE_ABSTRACTION_COLUMNS, exports.finance_abstraction_rows(s, e))
