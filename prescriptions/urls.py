from django.urls import path

from . import views

app_name = "prescriptions"

urlpatterns = [
    path("medicaments/suggestions/", views.medication_suggestions, name="suggestions"),
    path(
        "<int:prescription_id>/",
        views.prescription_detail,
        name="detail",
    ),
    path(
        "<int:prescription_id>/valider/",
        views.prescription_validate,
        name="validate",
    ),
    path(
        "<int:prescription_id>/corriger/",
        views.prescription_correct,
        name="correct",
    ),
    path(
        "<int:prescription_id>/imprimer/",
        views.prescription_document,
        name="document",
    ),
]
