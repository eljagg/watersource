"""URLs for the map page, layers and GIS export."""
from django.urls import path

from . import views

app_name = "maps"
urlpatterns = [
    path("", views.index, name="index"),
    path("layers/<slug:layer>.geojson", views.layer, name="layer"),
    path("export/", views.export_index, name="export"),
    path("export/watersource.gpkg", views.export_gpkg, name="export_gpkg"),
]
