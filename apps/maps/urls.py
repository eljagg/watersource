"""URLs for the map page, layers and GIS export."""
from django.urls import path

from . import views

app_name = "maps"
urlpatterns = [
    path("", views.index, name="index"),
    path("full/", views.full, name="full"),
    path("layers/<slug:layer>.geojson", views.layer, name="layer"),
    path("wmu/<slug:code>.json", views.wmu_detail, name="wmu_detail"),
    path("export/", views.export_index, name="export"),
    path("export/watersource.gpkg", views.export_gpkg, name="export_gpkg"),
]
