from pathlib import Path
from urllib.parse import unquote, urlsplit

from django.conf import settings
from django.contrib.staticfiles import finders
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET

from accounts.decorators import doctor_required
from consultations.models import Consultation
from patients.models import Patient


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
        .select_related("insurance_verified_by")
    )
    document_number = f"FP-{timezone.localdate().year}-{patient.pk:05d}"
    return _document_response(
        request,
        "documents/patient_sheet.html",
        {
            "patient": patient,
            "consultations": consultations,
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"fiche-patient-{patient.record_number}.pdf",
    )


@doctor_required
@require_GET
def consultation_report(request, consultation_id):
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient", "doctor"),
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
