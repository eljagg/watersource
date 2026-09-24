from django.urls import path

from . import views

app_name = "submissions"
urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:code>/new/", views.new_form, name="new_form"),
    path("<slug:code>/csv/", views.new_csv, name="new_csv"),
    path("<slug:code>/template.csv", views.template, name="template"),
    path("view/<int:pk>/", views.detail, name="detail"),
]
