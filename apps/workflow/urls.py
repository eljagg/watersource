from django.urls import path

from . import views

app_name = "workflow"
urlpatterns = [
    path("queue/", views.queue, name="queue"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/act/", views.act, name="act"),
]
