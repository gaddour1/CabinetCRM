from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from .models import MedicationLibraryEntry, Prescription, PrescriptionRevision


MEDICATION_FIELDS = (
    "name",
    "dosage",
    "pharmaceutical_form",
    "administration_route",
    "posology",
    "frequency",
    "duration",
    "quantity",
    "instructions",
)


def _apply_forms(prescription, prescription_form, medication_formset):
    prescription.recommendations = prescription_form.cleaned_data["recommendations"]
    prescription.save()

    medication_formset.instance = prescription
    medication_formset.save()
    for position, form in enumerate(medication_formset.ordered_forms):
        medication = form.instance
        if medication.position != position:
            medication.position = position
            medication.save(update_fields=["position"])
        if form.cleaned_data.get("save_to_library"):
            values = {
                field: getattr(medication, field)
                for field in MEDICATION_FIELDS
            }
            unique_values = {
                "doctor": prescription.prescriber,
                "name": medication.name,
                "dosage": medication.dosage,
                "pharmaceutical_form": medication.pharmaceutical_form,
            }
            MedicationLibraryEntry.objects.get_or_create(
                **unique_values,
                defaults={
                    field: values[field]
                    for field in MEDICATION_FIELDS
                    if field not in {"name", "dosage", "pharmaceutical_form"}
                },
            )


@transaction.atomic
def save_draft_prescription(
    *,
    consultation,
    prescriber,
    prescription_form,
    medication_formset,
):
    prescription = (
        Prescription.objects.select_for_update()
        .filter(consultation=consultation)
        .first()
    )
    if prescription and prescription.status != Prescription.Status.DRAFT:
        raise ValidationError(
            "Cette ordonnance est déjà validée. Utilisez la procédure de correction."
        )

    if prescription is None:
        has_medications = any(
            not form.cleaned_data.get("DELETE")
            and form.cleaned_data.get("name")
            for form in medication_formset.forms
        )
        if not (
            prescription_form.cleaned_data["recommendations"].strip()
            or has_medications
        ):
            return None
        prescription = Prescription(
            consultation=consultation,
            prescriber=prescriber,
        )
    _apply_forms(prescription, prescription_form, medication_formset)
    return prescription


@transaction.atomic
def validate_prescription(*, prescription_id, doctor):
    prescription = (
        Prescription.objects.select_for_update()
        .get(pk=prescription_id)
    )
    if prescription.status != Prescription.Status.DRAFT:
        raise ValidationError("Cette ordonnance a déjà été validée.")
    if not prescription.medications.exists():
        raise ValidationError(
            "Ajoutez au moins un médicament avant de valider l’ordonnance."
        )

    prescription.status = Prescription.Status.VALIDATED
    prescription.validated_at = timezone.now()
    prescription.validated_by = doctor
    prescription.save(
        update_fields=["status", "validated_at", "validated_by", "updated_at"]
    )
    return prescription


def _prescription_snapshot(prescription):
    return {
        "status": prescription.status,
        "recommendations": prescription.recommendations,
        "validated_at": (
            prescription.validated_at.isoformat()
            if prescription.validated_at
            else None
        ),
        "validated_by": (
            prescription.validated_by.get_full_name()
            or prescription.validated_by.username
            if prescription.validated_by
            else None
        ),
        "medications": [
            {
                field: getattr(medication, field)
                for field in ("position", *MEDICATION_FIELDS)
            }
            for medication in prescription.medications.order_by("position", "pk")
        ],
    }


@transaction.atomic
def correct_prescription(
    *,
    prescription_id,
    doctor,
    reason,
    prescription_form,
    medication_formset,
):
    prescription = (
        Prescription.objects.select_for_update()
        .get(pk=prescription_id)
    )
    if prescription.status != Prescription.Status.VALIDATED:
        raise ValidationError(
            "Seule une ordonnance validée peut être corrigée."
        )
    reason = reason.strip()
    if not reason:
        raise ValidationError("Le motif de correction est obligatoire.")
    if not medication_formset.ordered_forms:
        raise ValidationError(
            "Une ordonnance corrigée doit conserver au moins un médicament."
        )

    latest_version = (
        prescription.revisions.aggregate(version=Max("version_number"))["version"]
        or 0
    )
    PrescriptionRevision.objects.create(
        prescription=prescription,
        version_number=latest_version + 1,
        snapshot=_prescription_snapshot(prescription),
        reason=reason,
        corrected_by=doctor,
    )
    _apply_forms(prescription, prescription_form, medication_formset)
    return prescription
