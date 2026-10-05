"""Export routes (Finance & Accounts)."""
from django.urls import path

from . import views

app_name = "exports"
urlpatterns = [
    path("finance/", views.finance_index, name="finance"),
    path("finance/licences.csv", views.finance_licences_csv, name="finance_licences"),
    path("finance/abstraction.csv", views.finance_abstraction_csv, name="finance_abstraction"),
]
