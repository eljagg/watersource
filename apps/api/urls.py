from rest_framework.routers import DefaultRouter

from . import views

app_name = "api"
router = DefaultRouter()
router.register("parishes", views.ParishViewSet, basename="parish")
router.register("wells", views.WellViewSet, basename="well")
router.register("stations", views.StationViewSet, basename="station")
router.register("observations/well-water-levels", views.WellWaterLevelViewSet, basename="wellwaterlevel")
router.register("observations/abstractions", views.AbstractionViewSet, basename="abstraction")
router.register("observations/water-quality", views.WaterQualityViewSet, basename="waterquality")
router.register("licences", views.LicenceViewSet, basename="licence")
router.register("applications", views.ApplicationViewSet, basename="application")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("submissions", views.SubmissionViewSet, basename="submission")
urlpatterns: list = router.urls
