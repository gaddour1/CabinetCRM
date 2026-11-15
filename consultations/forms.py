from django import forms
from django.utils import timezone

from patients.models import Patient

from .models import Consultation, MedicalSuggestion, normalize_suggestion_text

TAG_FIELDS = (
    "reason",
    "medical_act",
    "medical_conduct",
    "biological_exams",
    "imaging_exams",
    "complementary_exams",
)


def normalize_tag_values(value):
    values = []
    seen = set()
    for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        tag = line.strip()
        normalized = normalize_suggestion_text(tag)
        if tag and normalized not in seen:
            values.append(tag)
            seen.add(normalized)
    return "\n".join(values)


class ConsultationForm(forms.ModelForm):
    consultation_fee = forms.DecimalField(
        label="Prix de la consultation (TND)",
        max_digits=10,
        decimal_places=3,
        min_value=0.001,
    )
    has_insurance = forms.TypedChoiceField(
        label="Le patient possède-t-il une assurance ?",
        choices=(("true", "Oui"), ("false", "Non")),
        coerce=lambda value: value == "true",
        widget=forms.RadioSelect,
        initial="false",
    )
    insurance_file_filled = forms.TypedChoiceField(
        label="Le dossier d’assurance est-il rempli ?",
        choices=(("true", "Oui"), ("false", "Non")),
        coerce=lambda value: value == "true",
        widget=forms.RadioSelect,
        required=False,
        empty_value=None,
    )
    insurance_verified = forms.BooleanField(
        label="Je confirme avoir vérifié les informations du dossier d’assurance",
        required=False,
    )

    class Meta:
        model = Consultation
        fields = [
            "patient",
            "consultation_date",
            "reason",
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
            "has_insurance",
            "insurance_file_filled",
            "insurance_type",
            "insurer",
            "affiliation_number",
            "insurance_comment",
        ]
        widgets = {
            "consultation_date": forms.DateInput(
                attrs={"type": "date"},
                format="%Y-%m-%d",
            ),
            "reason": forms.Textarea(
                attrs={
                    "rows": 2,
                    "data-tag-input": "",
                    "data-suggestion-category": "reason",
                    "autocomplete": "off",
                }
            ),
            "has_insurance": forms.RadioSelect,
            "insurance_file_filled": forms.RadioSelect,
            "insurance_comment": forms.Textarea(attrs={"rows": 2}),
            "clinical_other": forms.Textarea(attrs={"rows": 2}),
            "medical_act": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Acte réalisé…",
                    "data-tag-input": "",
                    "data-suggestion-category": "medical_act",
                    "autocomplete": "off",
                }
            ),
            "medical_conduct": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Conduite à tenir…",
                    "data-tag-input": "",
                    "data-suggestion-category": "medical_conduct",
                    "autocomplete": "off",
                }
            ),
            "biological_exams": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Bilan biologique…",
                    "data-tag-input": "",
                    "data-suggestion-category": "biological_exam",
                    "autocomplete": "off",
                }
            ),
            "imaging_exams": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Scanner, échographie…",
                    "data-tag-input": "",
                    "data-suggestion-category": "imaging_exam",
                    "autocomplete": "off",
                }
            ),
            "complementary_exams": forms.Textarea(
                attrs={
                    "rows": 2,
                    "data-tag-input": "",
                    "data-suggestion-category": "complementary_exam",
                    "autocomplete": "off",
                }
            ),
            "destination": forms.TextInput(
                attrs={
                    "data-suggestion-category": "destination",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        patient_id = kwargs.pop("patient_id", None)
        super().__init__(*args, **kwargs)
        self.fields["patient"].queryset = Patient.objects.filter(
            archived_at__isnull=True
        )
        if self.instance.pk:
            self.fields["patient"].disabled = True
            self.fields["consultation_fee"].initial = self.instance.invoice.consultation_fee
            self.initial["has_insurance"] = (
                "true" if self.instance.has_insurance else "false"
            )
            self.initial["insurance_file_filled"] = (
                "true"
                if self.instance.insurance_file_filled is True
                else (
                    "false"
                    if self.instance.insurance_file_filled is False
                    else None
                )
            )
            self.fields["insurance_verified"].initial = bool(
                self.instance.insurance_verified_at
            )
        else:
            self.initial["insurance_file_filled"] = None
            if patient_id and not self.is_bound:
                self.fields["patient"].initial = patient_id

    def clean_consultation_date(self):
        consultation_date = self.cleaned_data["consultation_date"]
        if consultation_date > timezone.localdate():
            raise forms.ValidationError(
                "La date de consultation ne peut pas être dans le futur."
            )
        return consultation_date

    def clean(self):
        cleaned_data = super().clean()
        has_insurance = cleaned_data.get("has_insurance")
        insurance_file_filled = cleaned_data.get("insurance_file_filled")
        verified = cleaned_data.get("insurance_verified")

        if not has_insurance:
            cleaned_data["insurance_file_filled"] = False
            cleaned_data["insurance_type"] = ""
            cleaned_data["insurer"] = ""
            cleaned_data["affiliation_number"] = ""
            cleaned_data["insurance_comment"] = ""
            cleaned_data["insurance_verified"] = False
        else:
            if insurance_file_filled is not None:
                cleaned_data["insurance_file_filled"] = bool(insurance_file_filled)
            if verified:
                missing_fields = []
                if cleaned_data["insurance_file_filled"] is not True:
                    missing_fields.append("insurance_file_filled")
                for field in ("insurance_type", "insurer", "affiliation_number"):
                    if not cleaned_data.get(field):
                        missing_fields.append(field)
                for field in missing_fields:
                    self.add_error(
                        field,
                        "Ce champ est nécessaire pour confirmer un dossier d’assurance complet.",
                    )
        for field in TAG_FIELDS:
            if field in cleaned_data:
                cleaned_data[field] = normalize_tag_values(cleaned_data[field])
        return cleaned_data


class MedicalSuggestionForm(forms.ModelForm):
    class Meta:
        model = MedicalSuggestion
        fields = ["category", "text"]

    def __init__(self, *args, doctor, **kwargs):
        super().__init__(*args, **kwargs)
        self.doctor = doctor
        if not self.instance.pk:
            self.instance.doctor = doctor

    def clean_text(self):
        text = self.cleaned_data["text"].strip()
        if not text:
            raise forms.ValidationError("La proposition ne peut pas être vide.")
        return text

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get("category")
        text = cleaned_data.get("text")
        if category and text:
            duplicate = MedicalSuggestion.objects.filter(
                doctor=self.doctor,
                category=category,
                normalized_text=normalize_suggestion_text(text),
            )
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                self.add_error("text", "Cette proposition existe déjà dans cette catégorie.")
        return cleaned_data
