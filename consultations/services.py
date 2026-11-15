from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Consultation


@transaction.atomic
def create_consultation(*, cleaned_data, doctor):
    consultation_data = dict(cleaned_data)
    insurance_verified = consultation_data.pop("insurance_verified", False)
    consultation = Consultation(
        **consultation_data,
        doctor=doctor,
    )
    if insurance_verified:
        consultation.insurance_verified_by = doctor
        consultation.insurance_verified_at = timezone.now()

    consultation.full_clean()
    consultation.save()
    return consultation


@transaction.atomic
def update_consultation(*, consultation_id, cleaned_data, doctor):
    consultation = Consultation.objects.select_for_update().get(pk=consultation_id)

    insurance_fields = (
        "has_insurance",
        "insurance_file_filled",
        "insurance_type",
        "insurer",
        "affiliation_number",
        "insurance_comment",
    )
    clinical_fields = (
        "blood_pressure",
        "temperature",
        "gad",
        "spo2",
        "heart_rate",
        "clinical_other",
        "medical_act",
        "medical_conduct",
        "biological_exams",
        "imaging_exams",
        "complementary_exams",
        "destination",
    )
    insurance_changed = any(
        getattr(consultation, field) != cleaned_data[field]
        for field in insurance_fields
    )
    insurance_verified = cleaned_data["insurance_verified"]

    consultation.consultation_date = cleaned_data["consultation_date"]
    consultation.reason = cleaned_data["reason"]
    consultation.consultation_fee = cleaned_data["consultation_fee"]
    for field in clinical_fields:
        setattr(consultation, field, cleaned_data[field])
    for field in insurance_fields:
        setattr(consultation, field, cleaned_data[field])

    if consultation.has_insurance and insurance_verified:
        consultation.insurance_verified_by = doctor
        consultation.insurance_verified_at = timezone.now()
    elif insurance_changed or not consultation.has_insurance:
        consultation.insurance_verified_by = None
        consultation.insurance_verified_at = None

    consultation.full_clean()
    consultation.save(
        update_fields=[
            "consultation_date",
            "reason",
            "consultation_fee",
            *clinical_fields,
            *insurance_fields,
            "insurance_verified_by",
            "insurance_verified_at",
        ]
    )
    return consultation
