from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("connexion/", include("django.contrib.auth.urls")),
    path("", include("core.urls")),
    path("patients/", include("patients.urls")),
    path("consultations/", include("consultations.urls")),
    path("ordonnances/", include("prescriptions.urls")),
    path("documents/", include("documents.urls")),
]
