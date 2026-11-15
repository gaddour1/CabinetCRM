from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.db.models import DecimalField, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import doctor_required
from billing.models import Invoice, Payment
from consultations.models import Consultation
from patients.models import Patient


def _invoice_queryset():
    return Invoice.objects.select_related("patient").annotate(
        paid_total=Coalesce(
            Sum("payments__amount"),
            Value(
                Decimal("0.000"),
                output_field=DecimalField(max_digits=10, decimal_places=3),
            ),
        )
    )


def _static_url_fetcher(url):
    from weasyprint import default_url_fetcher

    parsed_url = urlsplit(url)
    static_prefix = "/" + urlsplit(settings.STATIC_URL).path.strip("/") + "/"
    request_path = unquote(parsed_url.path)
    if parsed_url.scheme in {"http", "https"} and request_path.startswith(static_prefix):
        relative_path = request_path[len(static_prefix):]
        if (
            "\\" in relative_path
            or "\x00" in relative_path
            or ".." in relative_path.split("/")
        ):
            raise ValueError("Chemin de ressource statique invalide.")
        asset_path = finders.find(relative_path)
        if asset_path:
            return default_url_fetcher(Path(asset_path).resolve().as_uri())
        raise FileNotFoundError(f"Ressource statique introuvable : {relative_path}")
    raise ValueError("Seules les ressources statiques locales sont autorisées.")


def _document_response(request, template_name, context, filename):
    html_content = render_to_string(template_name, context, request=request)
    if request.GET.get("download") != "1":
        return HttpResponse(html_content)

    from weasyprint import HTML

    pdf_content = HTML(
        string=html_content,
        base_url=request.build_absolute_uri("/"),
        url_fetcher=_static_url_fetcher,
    ).write_pdf()
    response = HttpResponse(pdf_content, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@doctor_required
@require_GET
def patient_sheet(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    consultations = (
        Consultation.objects.filter(patient=patient)
        .select_related("doctor")
        .prefetch_related(
            Prefetch("invoice", queryset=_invoice_queryset())
        )
    )
    invoices = _invoice_queryset().filter(patient=patient).prefetch_related(
        "payments__created_by"
    )
    document_number = f"FP-{timezone.localdate().year}-{patient.pk:05d}"
    return _document_response(
        request,
        "documents/patient_sheet.html",
        {
            "patient": patient,
            "consultations": consultations,
            "invoices": invoices,
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"fiche-patient-{patient.record_number}.pdf",
    )


@doctor_required
@require_GET
def consultation_report(request, consultation_id):
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient", "doctor", "invoice"),
        pk=consultation_id,
    )
    document_number = f"CR-{timezone.localdate().year}-{consultation.pk:05d}"
    return _document_response(
        request,
        "documents/consultation_report.html",
        {
            "consultation": consultation,
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"compte-rendu-{consultation.reference}.pdf",
    )


@doctor_required
@require_GET
def invoice_document(request, invoice_id):
    invoice = get_object_or_404(_invoice_queryset(), pk=invoice_id)
    consultation = (
        Consultation.objects.filter(invoice=invoice)
        .select_related("doctor")
        .first()
    )
    document_number = f"FAC-{timezone.localdate().year}-{invoice.pk:05d}"
    return _document_response(
        request,
        "documents/invoice.html",
        {
            "invoice": invoice,
            "consultation": consultation,
            "payments": invoice.payments.select_related("created_by").all(),
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"facture-{invoice.number}.pdf",
    )


@doctor_required
@require_GET
def payment_receipt(request, payment_id):
    payment = get_object_or_404(
        Payment.objects.select_related("invoice__patient", "created_by"),
        pk=payment_id,
    )
    invoice = _invoice_queryset().get(pk=payment.invoice_id)
    document_number = f"REC-{timezone.localdate().year}-{payment.pk:05d}"
    return _document_response(
        request,
        "documents/payment_receipt.html",
        {
            "payment": payment,
            "invoice": invoice,
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"recu-{document_number}.pdf",
    )
