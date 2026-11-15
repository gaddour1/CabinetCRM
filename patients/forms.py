from django import forms
from django.utils import timezone

from .models import Patient


class PatientForm(forms.ModelForm):
    class Meta:
        model = Patient
        fields = [
            "first_name",
            "last_name",
            "date_of_birth",
            "sex",
            "cin",
            "phone",
            "address",
            "profession",
            "blood_group",
            "medical_history",
            "allergies",
            "usual_treatments",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "address": forms.Textarea(attrs={"rows": 2}),
            "medical_history": forms.Textarea(attrs={"rows": 3}),
            "allergies": forms.Textarea(attrs={"rows": 2}),
            "usual_treatments": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_date_of_birth(self):
        date_of_birth = self.cleaned_data.get("date_of_birth")
        if date_of_birth and date_of_birth > timezone.localdate():
            raise forms.ValidationError(
                "La date de naissance ne peut pas être dans le futur."
            )
        return date_of_birth

    def clean_blood_group(self):
        blood_group = self.cleaned_data.get("blood_group", "").strip().upper()
        allowed = {"", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
        if blood_group not in allowed:
            raise forms.ValidationError("Choisissez un groupe sanguin valide.")
        return blood_group
