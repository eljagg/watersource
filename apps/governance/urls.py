"""URLs: /executive/."""
from django.urls import path

from . import views

app_name = "governance"
urlpatterns = [
    path("", views.index, name="index"),
    path("milestones/<int:pk>/", views.milestone_action, name="milestone_action"),
]
