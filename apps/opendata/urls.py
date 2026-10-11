"""Open-data URLs."""
from django.urls import path

from . import views

app_name = "opendata"
urlpatterns = [
    path("", views.index, name="index"),
    path("documents/<int:pk>/", views.document, name="document"),
    path("documents/<int:pk>/<str:name>", views.document, name="document_named"),
    path("<slug:slug>/", views.dataset, name="dataset"),
    path("<slug:slug>.csv", views.dataset_csv, name="dataset_csv"),
    path("<slug:slug>.geojson", views.dataset_geojson, name="dataset_geojson"),
]
