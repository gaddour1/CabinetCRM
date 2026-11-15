from django import forms
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet

from .models import Prescription, PrescribedMedication


class PrescriptionForm(forms.ModelForm):
    class Meta:
        model = Prescription
        fields = ["recommendations"]
        widgets = {
            "recommendations": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "Conseils complémentaires au patient…",
                }
            ),
        }


class PrescriptionCorrectionForm(PrescriptionForm):
    correction_reason = forms.CharField(
        label="Motif de la correction",
        widget=forms.Textarea(attrs={"rows": 2}),
    )


class PrescribedMedicationForm(forms.ModelForm):
    save_to_library = forms.BooleanField(
        label="Enregistrer dans ma bibliothèque personnelle",
        required=False,
    )

    class Meta:
        model = PrescribedMedication
        fields = [
            "name",
            "dosage",
            "pharmaceutical_form",
            "administration_route",
            "posology",
            "frequency",
            "duration",
            "quantity",
            "instructions",
        ]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "autocomplete": "off",
                    "data-medication-name": "",
                }
            ),
            "dosage": forms.TextInput(attrs={"placeholder": "Ex. : 500 mg"}),
            "posology": forms.Textarea(attrs={"rows": 2}),
            "frequency": forms.TextInput(attrs={"placeholder": "Saisie par le médecin"}),
            "duration": forms.TextInput(attrs={"placeholder": "Saisie par le médecin"}),
            "quantity": forms.TextInput(),
            "instructions": forms.Textarea(attrs={"rows": 2}),
        }


class BasePrescribedMedicationFormSet(BaseInlineFormSet):
    ordering_widget = forms.HiddenInput
    deletion_widget = forms.HiddenInput


PrescribedMedicationFormSet = inlineformset_factory(
    Prescription,
    PrescribedMedication,
    form=PrescribedMedicationForm,
    formset=BasePrescribedMedicationFormSet,
    extra=1,
    can_delete=True,
    can_order=True,
)
