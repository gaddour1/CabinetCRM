from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.decorators import doctor_required
from documents.views import _document_response

from .forms import (
    PrescribedMedicationFormSet,
    PrescriptionCorrectionForm,
)
from .models import MedicationLibraryEntry, Prescription
from .services import correct_prescription, validate_prescription


@doctor_required
@require_GET
def medication_suggestions(request):
    query = request.GET.get("q", "").strip()
    if not query:
        return JsonResponse({"results": []})

    entries = MedicationLibraryEntry.objects.filter(
        doctor=request.user,
        name__icontains=query,
    ).order_by("name", "dosage")[:20]
    return JsonResponse(
        {
            "results": [
                {
                    "name": entry.name,
                    "dosage": entry.dosage,
                    "pharmaceutical_form": entry.pharmaceutical_form,
                    "administration_route": entry.administration_route,
                    "posology": entry.posology,
                    "frequency": entry.frequency,
                    "duration": entry.duration,
                    "quantity": entry.quantity,
                    "instructions": entry.instructions,
                }
                for entry in entries
            ]
        }
    )


def _prescription_queryset():
    return (
        Prescription.objects.select_related(
            "consultation__patient",
            "prescriber",
            "validated_by",
        )
        .prefetch_related("medications", "revisions__corrected_by")
    )


@doctor_required
@require_GET
def prescription_detail(request, prescription_id):
    prescription = get_object_or_404(
        _prescription_queryset(),
        pk=prescription_id,
    )
    return render(
        request,
        "prescriptions/prescription_detail.html",
        {"prescription": prescription},
    )


@doctor_required
@require_POST
def prescription_validate(request, prescription_id):
    try:
        prescription = validate_prescription(
            prescription_id=prescription_id,
            doctor=request.user,
        )
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    else:
        messages.success(request, "L’ordonnance a été validée.")
    return redirect("prescriptions:detail", prescription_id=prescription_id)


@doctor_required
def prescription_correct(request, prescription_id):
    prescription = get_object_or_404(
        _prescription_queryset(),
        pk=prescription_id,
    )
    if prescription.status != Prescription.Status.VALIDATED:
        messages.error(
            request,
            "Seule une ordonnance validée peut être corrigée.",
        )
        return redirect("prescriptions:detail", prescription_id=prescription.pk)

    form = PrescriptionCorrectionForm(
        request.POST or None,
        instance=prescription,
    )
    medication_formset = PrescribedMedicationFormSet(
        request.POST or None,
        instance=prescription,
        prefix="medications",
    )
    if request.method == "POST":
        form_is_valid = form.is_valid()
        formset_is_valid = medication_formset.is_valid()
        if form_is_valid and formset_is_valid:
            try:
                correct_prescription(
                    prescription_id=prescription.pk,
                    doctor=request.user,
                    reason=form.cleaned_data["correction_reason"],
                    prescription_form=form,
                    medication_formset=medication_formset,
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    "La correction est enregistrée et l’ancienne version est conservée.",
                )
                return redirect(
                    "prescriptions:detail",
                    prescription_id=prescription.pk,
                )

    return render(
        request,
        "prescriptions/prescription_correction_form.html",
        {
            "prescription": prescription,
            "form": form,
            "medication_formset": medication_formset,
        },
    )


@doctor_required
@require_GET
def prescription_document(request, prescription_id):
    prescription = get_object_or_404(
        _prescription_queryset(),
        pk=prescription_id,
    )
    document_number = f"ORD-{timezone.localdate().year}-{prescription.pk:05d}"
    return _document_response(
        request,
        "documents/prescription.html",
        {
            "prescription": prescription,
            "consultation": prescription.consultation,
            "patient": prescription.consultation.patient,
            "document_number": document_number,
            "generated_at": timezone.localtime(),
        },
        f"ordonnance-{prescription.consultation.reference}.pdf",
    )
