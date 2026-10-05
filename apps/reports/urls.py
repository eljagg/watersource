"""Dashboard and wall-display routes."""
from django.urls import path

from . import views

app_name = "reports"
urlpatterns = [
    path("dashboards/", views.index, name="index"),
    path("dashboards/<slug:slug>/", views.dashboard, name="dashboard"),
    path("dashboards/<slug:slug>/data/", views.dashboard_data, name="dashboard_data"),
    path("wall/", views.wall, name="wall"),
]
