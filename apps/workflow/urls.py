"""Staff review queue routes."""
from django.urls import path
from django.views.generic import RedirectView

from . import views

app_name = "workflow"
urlpatterns = [
    path("", RedirectView.as_view(pattern_name="workflow:queue", permanent=False), name="index"),  # v0.13.1: /workflow/ → the queue
    path("queue/", views.queue, name="queue"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/act/", views.act, name="act"),
]
