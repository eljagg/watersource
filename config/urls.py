from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

admin.site.site_header = "WaterSource admin console"
admin.site.site_title = "WaterSource admin console"
admin.site.index_title = "Administration"

urlpatterns = [
    path("", include("apps.core.urls", namespace="core")),
    path("accounts/", include("apps.accounts.urls", namespace="accounts")),
    path("licensing/", include("apps.lic.urls", namespace="lic")),
    path("submissions/", include("apps.submissions.urls", namespace="submissions")),
    path("workflow/", include("apps.workflow.urls", namespace="workflow")),
    path("", include("apps.reports.urls", namespace="reports")),
    path("api/v1/", include("apps.api.urls", namespace="api")),
    path("api/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="api-schema"), name="api-docs"),
    path("admin/", admin.site.urls),
]
if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
