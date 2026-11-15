from datetime import datetime

from django.contrib import messages
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from accounts.decorators import doctor_required
from consultations.models import Consultation

from .forms import PatientForm
from .models import Patient


PATIENT_SORTS = {
    "name": ("last_name", "first_name"),
    "first_name": ("first_name", "last_name"),
    "birth_date": ("date_of_birth", "last_name", "first_name"),
    "record_number": ("record_number",),
    "created": ("created_at",),
}


def _search_date(term):
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(term, date_format).date()
        except ValueError:
            continue
    return None


@doctor_required
def patient_list(request):
    show_archived = request.GET.get("archives") == "1"
    patients = Patient.objects.filter(
        archived_at__isnull=not show_archived
    )
    query = request.GET.get("q", "").strip()
    if query:
        for term in query.split():
            matching = (
                Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
                | Q(cin__icontains=term)
                | Q(phone__icontains=term)
                | Q(record_number__icontains=term)
            )
            date_value = _search_date(term)
            if date_value:
                matching |= Q(date_of_birth=date_value) | Q(created_at__date=date_value)
            patients = patients.filter(matching)

    sort = request.GET.get("sort", "name")
    if sort not in PATIENT_SORTS:
        sort = "name"
    direction = request.GET.get("direction", "asc")
    if direction not in {"asc", "desc"}:
        direction = "asc"
    patients = patients.order_by(
        *(f"-{field}" if direction == "desc" else field for field in PATIENT_SORTS[sort]),
        "-pk",
    )
    context = {
        "patients": patients,
        "query": query,
        "show_archived": show_archived,
        "sort": sort,
        "direction": direction,
        "sort_options": (
            ("name", "Nom"),
            ("first_name", "Prénom"),
            ("birth_date", "Date de naissance"),
            ("record_number", "Numéro de dossier"),
            ("created", "Date de création"),
        ),
    }
    if request.GET.get("partial") == "1":
        rows = render_to_string(
            "patients/partials/patient_rows.html",
            context,
            request=request,
        )
        return JsonResponse({"rows": rows, "count": patients.count()})
    return render(request, "patients/patient_list.html", context)


@doctor_required
def patient_create(request):
    form = PatientForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        patient = form.save()
        messages.success(request, "Le dossier patient a été créé.")
        return redirect("patients:detail", patient_id=patient.pk)
    return render(
        request,
        "patients/patient_form.html",
        {"form": form, "title": "Nouveau patient"},
    )


@doctor_required
def patient_detail(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    consultations = Consultation.objects.filter(patient=patient).select_related(
        "doctor", "insurance_verified_by"
    )
    return render(
        request,
        "patients/patient_detail.html",
        {
            "patient": patient,
            "consultations": consultations,
        },
    )


@doctor_required
def patient_update(request, patient_id):
    patient = get_object_or_404(Patient, pk=patient_id)
    form = PatientForm(request.POST or None, instance=patient)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Le dossier patient a été mis à jour.")
        return redirect("patients:detail", patient_id=patient.pk)
    return render(
        request,
        "patients/patient_form.html",
        {"form": form, "patient": patient, "title": "Modifier le dossier"},
    )


@doctor_required
def patient_archive(request, patient_id):
    if request.method != "POST":
        return redirect("patients:detail", patient_id=patient_id)
    patient = get_object_or_404(Patient, pk=patient_id)
    patient.archive()
    messages.success(request, "Le dossier a été archivé, sans suppression.")
    return redirect("patients:list")


@doctor_required
def patient_restore(request, patient_id):
    if request.method != "POST":
        return redirect("patients:detail", patient_id=patient_id)
    patient = get_object_or_404(Patient, pk=patient_id)
    patient.restore()
    messages.success(request, "Le dossier a été restauré.")
    return redirect("patients:detail", patient_id=patient.pk)


@doctor_required
def patient_delete(request, patient_id):
    if request.method != "POST":
        return redirect("patients:detail", patient_id=patient_id)
    patient = get_object_or_404(Patient, pk=patient_id)
    name = str(patient)
    patient.delete()
    messages.success(
        request,
        f"Le dossier de {name} et ses consultations ont été supprimés.",
    )
    return redirect("patients:list")
