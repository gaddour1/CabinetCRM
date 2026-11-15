from django.urls import path

from . import views

app_name = "documents"

urlpatterns = [
    path("patients/<int:patient_id>/", views.patient_sheet, name="patient_sheet"),
    path(
        "consultations/<int:consultation_id>/",
        views.consultation_report,
        name="consultation_report",
    ),
]
