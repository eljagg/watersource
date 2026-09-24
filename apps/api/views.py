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
        return self.queryset.visible_to(self.request.user if self.request.user.is_authenticated else None)


class WellViewSet(ClassifiedReadOnlyViewSet):
    queryset = Well.objects.select_related("parish", "basin", "wmu")
    serializer_class = serializers.WellSerializer
    filterset_fields = ["parish", "basin", "wmu", "use", "is_licensed", "is_abandoned"]
    search_fields = ["name", "aliases"]


class StationViewSet(ClassifiedReadOnlyViewSet):
    queryset = StreamflowStation.objects.select_related("parish", "river")
    serializer_class = serializers.StationSerializer
    filterset_fields = ["parish", "river", "is_active"]


class WellWaterLevelViewSet(ClassifiedReadOnlyViewSet):
    queryset = WellWaterLevel.objects.select_related("well")
    serializer_class = serializers.WellWaterLevelSerializer
    filterset_fields = {"well": ["exact"], "measured_at": ["gte", "lte"]}


class AbstractionViewSet(ClassifiedReadOnlyViewSet):
    queryset = AbstractionRecord.objects.select_related("licence", "well")
    serializer_class = serializers.AbstractionSerializer
    filterset_fields = {"licence": ["exact"], "well": ["exact"], "over_limit": ["exact"], "period_start": ["gte", "lte"]}


class WaterQualityViewSet(ClassifiedReadOnlyViewSet):
    queryset = WaterQualitySample.objects.select_related("well", "station", "spring")
    serializer_class = serializers.WaterQualitySerializer
    filterset_fields = {"well": ["exact"], "station": ["exact"], "source_type": ["exact"], "sampled_at": ["gte", "lte"]}


class ParishViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Parish.objects.all()
    serializer_class = serializers.ParishSerializer
    permission_classes = [permissions.AllowAny]


class StaffOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return u.is_authenticated and (u.is_staff_user or u.is_superuser)


class LicenceViewSet(viewsets.ReadOnlyModelViewSet):
    """Licence records for Finance & Accounts and internal reporting (ToR H.xiii). Staff only."""

    queryset = Licence.objects.select_related("licensee", "parish")
    serializer_class = serializers.LicenceSerializer
    permission_classes = [StaffOnly]
    filterset_fields = ["status", "parish", "water_source"]


class ApplicationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LicenceApplication.objects.select_related("parish")
    serializer_class = serializers.ApplicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ["status", "parish", "water_source"]
    lookup_field = "reference"

    def get_queryset(self):
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
        from django.http import HttpResponse

        cat = self.get_object()
        return HttpResponse(csv_template(cat.current_version), content_type="text/csv")


class SubmissionViewSet(mixins.CreateModelMixin, mixins.RetrieveModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """Programmatic submission (ToR F.7.iv(a)). POST rows for a category; the same
    validation and approval workflow applies as for the web form and CSV."""

    permission_classes = [permissions.IsAuthenticated]
    serializer_class = serializers.SubmissionSerializer
    queryset = Submission.objects.none()

    def get_queryset(self):
        qs = Submission.objects.select_related("category_version__category").prefetch_related("records")
        u = self.request.user
        if getattr(self, "swagger_fake_view", False) or not u.is_authenticated:
            return qs.none()
        return qs if (u.is_staff_user or u.is_superuser) else qs.filter(submitter=u)

    def create(self, request, *args, **kwargs):
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
