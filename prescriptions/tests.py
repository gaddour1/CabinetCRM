from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import date

from accounts.models import User
from consultations.models import Consultation
from patients.models import Patient

from .forms import PrescribedMedicationFormSet, PrescriptionForm
from .models import (
    MedicationLibraryEntry,
    Prescription,
    PrescriptionRevision,
    PrescribedMedication,
)
from .services import (
    correct_prescription,
    save_draft_prescription,
    validate_prescription,
)


class PrescriptionWorkflowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username="doctor",
            password="test-password",
            role=User.Role.DOCTOR,
            first_name="Docteur",
            last_name="Exemple",
        )
        self.patient = Patient.objects.create(
            first_name="Patient",
            last_name="Fictif",
            date_of_birth=date(1985, 1, 1),
        )
        self.client.force_login(self.doctor)

    def create_consultation(self):
        return Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            consultation_date=timezone.localdate(),
            reason="Consultation fictive",
        )

    def create_medication(self, prescription, name="Médicament A"):
        return PrescribedMedication.objects.create(
            prescription=prescription,
            name=name,
            dosage="500 mg",
            pharmaceutical_form=PrescribedMedication.PharmaceuticalForm.TABLET,
            administration_route=PrescribedMedication.AdministrationRoute.ORAL,
            posology="Un comprimé selon l’avis du médecin",
            frequency="Selon les instructions du médecin",
            duration="Durée déterminée par le médecin",
        )

    def medication_formset_data(
        self,
        medications,
        *,
        initial_count=0,
        deleted=(),
        save_to_library=(),
    ):
        data = {
            "medications-TOTAL_FORMS": str(len(medications)),
            "medications-INITIAL_FORMS": str(initial_count),
            "medications-MIN_NUM_FORMS": "0",
            "medications-MAX_NUM_FORMS": "1000",
        }
        for index, medication in enumerate(medications):
            prefix = f"medications-{index}-"
            for field in (
                "name",
                "dosage",
                "pharmaceutical_form",
                "administration_route",
                "posology",
                "frequency",
                "duration",
                "quantity",
                "instructions",
            ):
                data[prefix + field] = medication.get(field, "")
            data[prefix + "ORDER"] = str(index)
            if medication.get("id"):
                data[prefix + "id"] = str(medication["id"])
            if index in deleted:
                data[prefix + "DELETE"] = "on"
            if index in save_to_library:
                data[prefix + "save_to_library"] = "on"
        return data

    def consultation_data(self, medication_data, recommendations="Conseils fictifs"):
        return {
            "patient": str(self.patient.pk),
            "consultation_date": timezone.localdate().isoformat(),
            "reason": "Consultation fictive",
            "has_insurance": "false",
            "insurance_file_filled": "false",
            "recommendations": recommendations,
            **medication_data,
        }

    def medication_values(self, name):
        return {
            "name": name,
            "dosage": "250 mg",
            "pharmaceutical_form": PrescribedMedication.PharmaceuticalForm.CAPSULE,
            "administration_route": PrescribedMedication.AdministrationRoute.ORAL,
            "posology": "Posologie saisie par le médecin",
            "frequency": "Fréquence saisie par le médecin",
            "duration": "Durée saisie par le médecin",
            "quantity": "10",
            "instructions": "Instructions saisies par le médecin",
        }

    def test_consultation_creates_one_prescription_with_multiple_medications(self):
        medications = [
            self.medication_values("Médicament A"),
            self.medication_values("Médicament B"),
        ]
        response = self.client.post(
            reverse("consultations:create"),
            self.consultation_data(
                self.medication_formset_data(
                    medications,
                    save_to_library=(0,),
                )
            ),
        )

        consultation = Consultation.objects.get()
        prescription = Prescription.objects.get()
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        self.assertEqual(prescription.consultation, consultation)
        self.assertEqual(prescription.consultation.patient, self.patient)
        self.assertEqual(prescription.prescriber, self.doctor)
        self.assertEqual(prescription.status, Prescription.Status.DRAFT)
        self.assertEqual(prescription.medications.count(), 2)
        self.assertEqual(MedicationLibraryEntry.objects.count(), 1)

    def test_consultation_form_uses_icon_controls_and_clear_footer_actions(self):
        response = self.client.get(
            reverse("consultations:create"),
            {"patient": self.patient.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-label="Monter le médicament"')
        self.assertContains(response, 'aria-label="Descendre le médicament"')
        self.assertContains(response, 'aria-label="Supprimer le médicament"')
        self.assertContains(response, "Annuler")
        self.assertContains(response, "Enregistrer")
        self.assertNotContains(response, "↑ Monter")
        self.assertNotContains(response, "↓ Descendre")

    def test_draft_can_be_modified_and_medication_removed_before_validation(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
            recommendations="Conseils initiaux",
        )
        medication = self.create_medication(prescription)
        medications = [
            {
                **self.medication_values("Médicament corrigé"),
                "id": medication.pk,
            },
            self.medication_values("Médicament à supprimer"),
        ]
        data = self.medication_formset_data(
            medications,
            initial_count=1,
            deleted=(1,),
        )
        prescription_form = PrescriptionForm(
            {"recommendations": "Conseils mis à jour"},
            instance=prescription,
        )
        medication_formset = PrescribedMedicationFormSet(
            data,
            instance=prescription,
            prefix="medications",
        )
        self.assertTrue(prescription_form.is_valid(), prescription_form.errors)
        self.assertTrue(medication_formset.is_valid(), medication_formset.errors)

        save_draft_prescription(
            consultation=consultation,
            prescriber=self.doctor,
            prescription_form=prescription_form,
            medication_formset=medication_formset,
        )

        prescription.refresh_from_db()
        self.assertEqual(prescription.recommendations, "Conseils mis à jour")
        self.assertEqual(prescription.medications.count(), 1)
        self.assertEqual(prescription.medications.get().name, "Médicament corrigé")

    def test_medical_instructions_must_be_entered_by_the_prescriber(self):
        formset = PrescribedMedicationFormSet(
            self.medication_formset_data(
                [{"name": "Médicament sans instructions"}],
            ),
            instance=Prescription(consultation=self.create_consultation()),
            prefix="medications",
        )

        self.assertFalse(formset.is_valid())
        self.assertIn("posology", formset.forms[0].errors)
        self.assertIn("frequency", formset.forms[0].errors)
        self.assertIn("duration", formset.forms[0].errors)

    def test_medications_can_be_reordered(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
        )
        first = self.create_medication(prescription, "Premier médicament")
        second = self.create_medication(prescription, "Deuxième médicament")
        medications = [
            {
                **self.medication_values(first.name),
                "id": first.pk,
            },
            {
                **self.medication_values(second.name),
                "id": second.pk,
            },
        ]
        data = self.medication_formset_data(medications, initial_count=2)
        data["medications-0-ORDER"] = "1"
        data["medications-1-ORDER"] = "0"
        prescription_form = PrescriptionForm(
            {"recommendations": ""},
            instance=prescription,
        )
        medication_formset = PrescribedMedicationFormSet(
            data,
            instance=prescription,
            prefix="medications",
        )
        self.assertTrue(prescription_form.is_valid())
        self.assertTrue(medication_formset.is_valid(), medication_formset.errors)

        save_draft_prescription(
            consultation=consultation,
            prescriber=self.doctor,
            prescription_form=prescription_form,
            medication_formset=medication_formset,
        )

        self.assertEqual(
            list(
                prescription.medications.values_list("name", flat=True).order_by(
                    "position"
                )
            ),
            ["Deuxième médicament", "Premier médicament"],
        )

    def test_validation_requires_medication_and_locks_draft_editing(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
        )
        with self.assertRaises(ValidationError):
            validate_prescription(prescription_id=prescription.pk, doctor=self.doctor)

        self.create_medication(prescription)
        validated = validate_prescription(
            prescription_id=prescription.pk,
            doctor=self.doctor,
        )
        self.assertEqual(validated.status, Prescription.Status.VALIDATED)
        self.assertIsNotNone(validated.validated_at)
        self.assertEqual(validated.validated_by, self.doctor)
        with self.assertRaises(ValidationError):
            validate_prescription(prescription_id=prescription.pk, doctor=self.doctor)

        form = PrescriptionForm(
            {"recommendations": "Modification interdite"},
            instance=prescription,
        )
        formset = PrescribedMedicationFormSet(
            self.medication_formset_data(
                [
                    {
                        **self.medication_values("Autre médicament"),
                        "id": prescription.medications.get().pk,
                    }
                ],
                initial_count=1,
            ),
            instance=prescription,
            prefix="medications",
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(formset.is_valid(), formset.errors)
        with self.assertRaises(ValidationError):
            save_draft_prescription(
                consultation=prescription.consultation,
                prescriber=self.doctor,
                prescription_form=form,
                medication_formset=formset,
            )

    def test_correction_preserves_previous_version_and_reason(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
            status=Prescription.Status.VALIDATED,
            recommendations="Conseils précédents",
            validated_at=timezone.now(),
            validated_by=self.doctor,
        )
        original = self.create_medication(prescription, "Ancien médicament")
        detail_url = reverse("prescriptions:detail", args=[prescription.pk])
        correction_url = reverse("prescriptions:correct", args=[prescription.pk])
        self.assertEqual(self.client.get(detail_url).status_code, 200)
        correction_form_page = self.client.get(correction_url)
        self.assertEqual(correction_form_page.status_code, 200)
        self.assertContains(correction_form_page, "Motif de la correction")

        form = PrescriptionForm(
            {"recommendations": "Conseils corrigés"},
            instance=prescription,
        )
        formset = PrescribedMedicationFormSet(
            self.medication_formset_data(
                [
                    {
                        **self.medication_values("Médicament corrigé"),
                        "id": original.pk,
                    }
                ],
                initial_count=1,
            ),
            instance=prescription,
            prefix="medications",
        )
        self.assertTrue(form.is_valid())
        self.assertTrue(formset.is_valid(), formset.errors)

        correct_prescription(
            prescription_id=prescription.pk,
            doctor=self.doctor,
            reason="Correction fictive nécessaire",
            prescription_form=form,
            medication_formset=formset,
        )

        revision = PrescriptionRevision.objects.get(prescription=prescription)
        self.assertEqual(revision.version_number, 1)
        self.assertEqual(revision.reason, "Correction fictive nécessaire")
        self.assertEqual(revision.corrected_by, self.doctor)
        self.assertEqual(
            revision.snapshot["recommendations"],
            "Conseils précédents",
        )
        self.assertEqual(
            revision.snapshot["medications"][0]["name"],
            "Ancien médicament",
        )
        self.assertEqual(
            prescription.medications.get().name,
            "Médicament corrigé",
        )
        self.assertEqual(prescription.status, Prescription.Status.VALIDATED)
        corrected_detail = self.client.get(detail_url)
        self.assertEqual(corrected_detail.status_code, 200)
        self.assertContains(corrected_detail, "Ancien médicament")
        self.assertContains(corrected_detail, "Correction fictive nécessaire")

    def test_personal_suggestions_do_not_expose_another_doctors_library(self):
        other_doctor = User.objects.create_user(
            username="autre-medecin",
            password="test-password",
            role=User.Role.DOCTOR,
        )
        MedicationLibraryEntry.objects.create(
            doctor=self.doctor,
            name="Médicament personnel",
        )
        MedicationLibraryEntry.objects.create(
            doctor=other_doctor,
            name="Médicament confidentiel",
        )

        response = self.client.get(
            reverse("prescriptions:suggestions"),
            {"q": "Médicament"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [entry["name"] for entry in response.json()["results"]],
            ["Médicament personnel"],
        )

    def test_patient_history_and_pdf_use_prescription(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
            status=Prescription.Status.VALIDATED,
            recommendations="Conseils fictifs",
            validated_at=timezone.now(),
            validated_by=self.doctor,
        )
        self.create_medication(prescription)

        history = self.client.get(
            reverse("patients:detail", args=[self.patient.pk])
        )
        self.assertEqual(history.status_code, 200)
        self.assertContains(history, "Historique des ordonnances")
        self.assertContains(history, reverse("prescriptions:detail", args=[prescription.pk]))
        consultation_detail = self.client.get(
            reverse("consultations:detail", args=[consultation.pk])
        )
        self.assertEqual(consultation_detail.status_code, 200)
        self.assertContains(consultation_detail, "Voir l’ordonnance")

        preview = self.client.get(
            reverse("prescriptions:document", args=[prescription.pk])
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, "ORDONNANCE MÉDICALE")
        self.assertContains(preview, "Médicament A")
        self.assertContains(preview, "Signature et cachet du médecin")

        pdf = self.client.get(
            reverse("prescriptions:document", args=[prescription.pk]),
            {"download": "1"},
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf["Content-Type"], "application/pdf")
        self.assertTrue(pdf.content.startswith(b"%PDF-"))

    def test_validation_endpoint_requires_confirmation_post_and_medical_access(self):
        consultation = self.create_consultation()
        prescription = Prescription.objects.create(
            consultation=consultation,
            prescriber=self.doctor,
        )
        self.create_medication(prescription)
        validate_url = reverse("prescriptions:validate", args=[prescription.pk])

        self.assertEqual(self.client.get(validate_url).status_code, 405)
        response = self.client.post(validate_url)
        self.assertRedirects(
            response,
            reverse("prescriptions:detail", args=[prescription.pk]),
        )
        prescription.refresh_from_db()
        self.assertEqual(prescription.status, Prescription.Status.VALIDATED)
        edit_page = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )
        self.assertEqual(edit_page.status_code, 200)
        self.assertNotContains(edit_page, 'name="medications-0-name"')
        self.assertContains(edit_page, "protégée contre les modifications directes")

        inactive_user = User.objects.create_user(
            username="inactive",
            password="test-password",
            role="",
        )
        self.client.force_login(inactive_user)
        self.assertEqual(
            self.client.get(
                reverse("prescriptions:detail", args=[prescription.pk])
            ).status_code,
            403,
        )
