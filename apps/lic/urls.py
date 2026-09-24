from django.urls import path

from . import views

app_name = "lic"
urlpatterns = [
    path("applications/", views.application_list, name="application_list"),
    path("applications/new/", views.application_create, name="application_create"),
    path("applications/<str:reference>/", views.application_detail, name="application_detail"),
    path("applications/<str:reference>/upload/", views.application_upload, name="application_upload"),
    path("applications/<str:reference>/submit/", views.application_submit, name="application_submit"),
    path("documents/<int:pk>/download/", views.document_download, name="document_download"),
    path("licences/", views.licence_list, name="licence_list"),
    path("licences/<str:number>/", views.licence_detail, name="licence_detail"),
]
