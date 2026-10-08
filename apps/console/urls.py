"""Unit console URLs."""
from django.urls import path

from . import views

app_name = "console"
urlpatterns = [
    path("", views.index, name="index"),
    path("issues/<int:pk>/resolve/", views.resolve, name="resolve"),
    path("members/<int:pk>/unlock/", views.unlock, name="unlock"),
    path("adoption/", views.signoff, name="signoff"),
]
