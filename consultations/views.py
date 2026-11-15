from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, F, IntegerField, Q, Value, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.decorators import doctor_required
from prescriptions.forms import (
    PrescribedMedicationFormSet,
    PrescriptionForm,
)
from prescriptions.models import Prescription
from prescriptions.services import save_draft_prescription

from .forms import ConsultationForm, MedicalSuggestionForm
from .models import Consultation, MedicalSuggestion, normalize_suggestion_text
from .services import create_consultation, update_consultation


CONSULTATION_SORTS = {
    "date": ("consultation_date", "created_at"),
    "patient": ("patient__last_name", "patient__first_name"),
    "reason": ("reason",),
    "insurance": ("insurance_rank",),
    "reference": ("reference",),
}


def _annotated_consultations():
    return Consultation.objects.select_related(
        "patient",
        "doctor",
        "insurance_verified_by",
    ).annotate(
        insurance_rank=Case(
            When(has_insurance=False, then=Value(0)),
            When(
                has_insurance=True,
                insurance_file_filled=True,
                insurance_type__gt="",
                insurer__gt="",
                affiliation_number__gt="",
                insurance_verified_at__isnull=False,
                then=Value(2),
            ),
            default=Value(1),
            output_field=IntegerField(),
        ),
    )


def _search_date(term):
    from datetime import datetime

    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(term, date_format).date()
        except ValueError:
            continue
    return None


def _prescription_forms_for_consultation(consultation, doctor, data=None):
    prescription = None
    if consultation.pk:
        prescription = Prescription.objects.filter(consultation=consultation).first()
    if prescription and prescription.status == Prescription.Status.VALIDATED:
        return None, None, prescription

    if prescription is None:
        prescription = Prescription(consultation=consultation, prescriber=doctor)
    return (
        PrescriptionForm(data, instance=prescription),
        PrescribedMedicationFormSet(
            data,
            instance=prescription,
            prefix="medications",
        ),
        prescription,
    )


@doctor_required
@require_GET
def consultation_list(request):
    consultations = _annotated_consultations()
    query = request.GET.get("q", "").strip()
    if query:
        for term in query.split():
            matching = (
                Q(reference__icontains=term)
                | Q(patient__first_name__icontains=term)
                | Q(patient__last_name__icontains=term)
                | Q(patient__cin__icontains=term)
                | Q(patient__phone__icontains=term)
                | Q(patient__record_number__icontains=term)
                | Q(reason__icontains=term)
            )
            date_value = _search_date(term)
            if date_value:
                matching |= Q(patient__date_of_birth=date_value)
            consultations = consultations.filter(matching)

    sort = request.GET.get("sort", "date")
    if sort not in CONSULTATION_SORTS:
        sort = "date"
    direction = request.GET.get("direction", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"
    order_by = CONSULTATION_SORTS[sort]
    consultations = consultations.order_by(
        *(f"-{field}" if direction == "desc" else field for field in order_by),
        "-pk",
    )
    context = {
        "consultations": consultations,
        "query": query,
        "sort": sort,
        "direction": direction,
        "sort_options": (
            ("date", "Date de consultation"),
            ("patient", "Patient (A–Z)"),
            ("reason", "Motif"),
            ("insurance", "Statut de l’assurance"),
            ("reference", "Référence"),
        ),
    }
    if request.GET.get("partial") == "1":
        rows = render_to_string(
            "consultations/partials/consultation_rows.html",
            context,
            request=request,
        )
        return JsonResponse(
            {"rows": rows, "count": consultations.count()}
        )
    return render(
        request,
        "consultations/consultation_list.html",
        context,
    )


@doctor_required
@require_http_methods(["GET", "POST"])
def consultation_create(request):
    form = ConsultationForm(
        request.POST or None,
        patient_id=request.GET.get("patient"),
    )
    is_post = request.method == "POST"
    consultation_is_valid = form.is_valid() if is_post else False
    prescription_data = (
        request.POST
        if is_post and "medications-TOTAL_FORMS" in request.POST
        else None
    )
    prescription_form, medication_formset, prescription = (
        _prescription_forms_for_consultation(
            form.instance,
            request.user,
            prescription_data,
        )
    )
    prescription_is_valid = True
    if (
        prescription_form is not None
        and medication_formset is not None
        and prescription_data is not None
    ):
        prescription_is_valid = prescription_form.is_valid()
        prescription_is_valid = medication_formset.is_valid() and prescription_is_valid

    if is_post and consultation_is_valid and prescription_is_valid:
        try:
            with transaction.atomic():
                consultation = create_consultation(
                    cleaned_data=form.cleaned_data,
                    doctor=request.user,
                )
                if (
                    prescription_form is not None
                    and medication_formset is not None
                    and prescription_data is not None
                ):
                    save_draft_prescription(
                        consultation=consultation,
                        prescriber=request.user,
                        prescription_form=prescription_form,
                        medication_formset=medication_formset,
                    )
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field, errors in error.message_dict.items():
                    for message in errors:
                        form.add_error(field, message)
            else:
                form.add_error(None, error)
        else:
            messages.success(
                request,
                f"La consultation {consultation.reference} a été créée.",
            )
            return redirect(
                "consultations:detail",
                consultation_id=consultation.pk,
            )
    return render(
        request,
        "consultations/consultation_form.html",
        {
            "form": form,
            "is_edit": False,
            "prescription_form": prescription_form,
            "medication_formset": medication_formset,
            "prescription": prescription,
            "prescription_suggestions_url": "prescriptions:suggestions",
        },
    )


@doctor_required
@require_http_methods(["GET", "POST"])
def consultation_update(request, consultation_id):
    consultation = get_object_or_404(Consultation, pk=consultation_id)
    form = ConsultationForm(
        request.POST or None,
        instance=consultation,
    )
    is_post = request.method == "POST"
    consultation_is_valid = form.is_valid() if is_post else False
    prescription_data = (
        request.POST
        if is_post and "medications-TOTAL_FORMS" in request.POST
        else None
    )
    prescription_form, medication_formset, prescription = (
        _prescription_forms_for_consultation(
            consultation,
            request.user,
            prescription_data,
        )
    )
    prescription_is_valid = True
    if (
        prescription_form is not None
        and medication_formset is not None
        and prescription_data is not None
    ):
        prescription_is_valid = prescription_form.is_valid()
        prescription_is_valid = medication_formset.is_valid() and prescription_is_valid

    if is_post and consultation_is_valid and prescription_is_valid:
        try:
            with transaction.atomic():
                updated_consultation = update_consultation(
                    consultation_id=consultation.pk,
                    cleaned_data=form.cleaned_data,
                    doctor=request.user,
                )
                if (
                    prescription_form is not None
                    and medication_formset is not None
                    and prescription_data is not None
                ):
                    save_draft_prescription(
                        consultation=updated_consultation,
                        prescriber=request.user,
                        prescription_form=prescription_form,
                        medication_formset=medication_formset,
                    )
        except ValidationError as error:
            if hasattr(error, "message_dict"):
                for field, errors in error.message_dict.items():
                    for message in errors:
                        form.add_error(field, message)
            else:
                form.add_error(None, error)
        else:
            messages.success(request, "La consultation a été mise à jour.")
            return redirect(
                "consultations:detail",
                consultation_id=updated_consultation.pk,
            )
    return render(
        request,
        "consultations/consultation_form.html",
        {
            "form": form,
            "consultation": consultation,
            "is_edit": True,
            "prescription_form": prescription_form,
            "medication_formset": medication_formset,
            "prescription": prescription,
            "prescription_suggestions_url": "prescriptions:suggestions",
        },
    )


@doctor_required
@require_GET
def consultation_detail(request, consultation_id):
    consultation = get_object_or_404(_annotated_consultations(), pk=consultation_id)
    prescription = Prescription.objects.filter(consultation=consultation).first()
    return render(
        request,
        "consultations/consultation_detail.html",
        {"consultation": consultation, "prescription": prescription},
    )


@doctor_required
@require_POST
def consultation_delete(request, consultation_id):
    consultation = get_object_or_404(
        Consultation.objects.select_related("patient"),
        pk=consultation_id,
    )
    reference = consultation.reference
    consultation.delete()
    messages.success(request, f"La consultation {reference} a été supprimée.")
    return redirect("consultations:list")


@doctor_required
@require_GET
def medical_suggestions_api(request):
    category = request.GET.get("category", "")
    valid_categories = {value for value, _label in MedicalSuggestion.Category.choices}
    if category not in valid_categories:
        return JsonResponse({"error": "Catégorie de suggestion invalide."}, status=400)

    query = normalize_suggestion_text(request.GET.get("q", "").strip())
    suggestions = (
        MedicalSuggestion.objects.filter(category=category, is_active=True)
        .filter(Q(doctor=request.user) | Q(doctor__isnull=True))
    )
    if query:
        suggestions = suggestions.filter(normalized_text__contains=query)

    suggestions = suggestions.annotate(
        owner_rank=Case(
            When(doctor=request.user, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("-usage_count", "owner_rank", "text")

    results = []
    seen = set()
    for suggestion in suggestions[:20]:
        normalized_text = suggestion.normalized_text
        if normalized_text in seen:
            continue
        seen.add(normalized_text)
        results.append(
            {"id": suggestion.pk, "text": suggestion.text}
        )
        if len(results) == 8:
            break
    return JsonResponse({"results": results})


@doctor_required
@require_POST
def medical_suggestion_use(request, suggestion_id):
    suggestion = get_object_or_404(
        MedicalSuggestion.objects.filter(
            Q(doctor=request.user) | Q(doctor__isnull=True),
            is_active=True,
        ),
        pk=suggestion_id,
    )
    MedicalSuggestion.objects.filter(pk=suggestion.pk).update(
        usage_count=F("usage_count") + 1
    )
    return HttpResponse(status=204)


@doctor_required
@require_GET
def medical_suggestion_list(request):
    include_archived = request.GET.get("archives") == "1"
    suggestions = MedicalSuggestion.objects.filter(
        Q(doctor=request.user) | Q(doctor__isnull=True)
    )
    if not include_archived:
        suggestions = suggestions.filter(is_active=True)
    return render(
        request,
        "consultations/suggestion_list.html",
        {
            "suggestions": suggestions,
            "include_archived": include_archived,
        },
    )


@doctor_required
@require_http_methods(["GET", "POST"])
def medical_suggestion_create(request):
    form = MedicalSuggestionForm(
        request.POST or None,
        doctor=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La suggestion a été ajoutée.")
        return redirect("consultations:suggestions")
    return render(
        request,
        "consultations/suggestion_form.html",
        {"form": form, "is_edit": False},
    )


@doctor_required
@require_http_methods(["GET", "POST"])
def medical_suggestion_update(request, suggestion_id):
    suggestion = get_object_or_404(
        MedicalSuggestion,
        pk=suggestion_id,
        doctor=request.user,
    )
    form = MedicalSuggestionForm(
        request.POST or None,
        instance=suggestion,
        doctor=request.user,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "La suggestion a été modifiée.")
        return redirect("consultations:suggestions")
    return render(
        request,
        "consultations/suggestion_form.html",
        {"form": form, "is_edit": True, "suggestion": suggestion},
    )


@doctor_required
@require_POST
def medical_suggestion_toggle_archive(request, suggestion_id):
    suggestion = get_object_or_404(
        MedicalSuggestion,
        pk=suggestion_id,
        doctor=request.user,
    )
    suggestion.is_active = not suggestion.is_active
    suggestion.save(update_fields=["is_active"])
    status = "réactivée" if suggestion.is_active else "archivée"
    messages.success(request, f"La suggestion a été {status}.")
    return redirect("consultations:suggestions")
