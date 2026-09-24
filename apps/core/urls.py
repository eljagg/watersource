from django.urls import path

from . import views

app_name = "core"
urlpatterns = [
    path("", views.home, name="home"),
    path("healthz", views.healthz, name="healthz"),
    path("notifications/", views.notifications, name="notifications"),
    path("notifications/<int:pk>/read/", views.notification_read, name="notification_read"),
]
urlpatterns += [path("privacy/", views.privacy, name="privacy")]
