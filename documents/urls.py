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
    path("factures/<int:invoice_id>/", views.invoice_document, name="invoice"),
    path(
        "paiements/<int:payment_id>/",
        views.payment_receipt,
        name="payment_receipt",
    ),
]
