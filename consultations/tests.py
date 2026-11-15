from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from patients.models import Patient

from .forms import ConsultationForm
from .models import Consultation, MedicalSuggestion


class ConsultationWorkflowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username="doctor",
            password="test-password-only",
            role=User.Role.DOCTOR,
            first_name="Docteur",
        )
        self.patient = Patient.objects.create(
            first_name="Patient",
            last_name="Fictif",
            cin="00000000",
        )
        self.client.force_login(self.doctor)

    def create_consultation(self, **overrides):
        values = {
            "patient": self.patient,
            "consultation_date": timezone.localdate(),
            "reason": "Motif fictif de test",
            "has_insurance": False,
            "insurance_file_filled": False,
            "insurance_type": "",
            "insurer": "",
            "affiliation_number": "",
            "insurance_comment": "",
        }
        values.update(overrides)
        return Consultation.objects.create(
            **values,
            doctor=self.doctor,
        )

    def test_consultation_list_searches_birth_date_and_returns_sorted_partial_rows(self):
        self.patient.date_of_birth = timezone.localdate() - timedelta(days=10000)
        self.patient.save(update_fields=["date_of_birth"])
        consultation = self.create_consultation()

        response = self.client.get(
            reverse("consultations:list"),
            {
                "q": consultation.patient.date_of_birth.strftime("%d/%m/%Y"),
                "sort": "patient",
                "direction": "asc",
                "partial": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertIn(consultation.reference, response.json()["rows"])

    def test_new_consultation_saves_optional_fee(self):
        response = self.client.post(
            reverse("consultations:create"),
            {
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Consultation fictive",
                "consultation_fee": "72.500",
                "blood_pressure": "120/80",
                "temperature": "37.2",
                "gad": "1.10",
                "spo2": "98",
                "heart_rate": "72",
                "clinical_other": "Observation fictive",
                "medical_act": "Examen clinique fictif",
                "medical_conduct": "Conduite fictive",
                "biological_exams": "Bilan sanguin fictif",
                "imaging_exams": "Scanner fictif",
                "complementary_exams": "Bilan sanguin fictif",
                "destination": "Orientation personnalisée",
                "has_insurance": "false",
                "insurance_file_filled": "false",
                "insurance_type": "",
                "insurer": "",
                "affiliation_number": "",
                "insurance_comment": "",
            },
        )

        consultation = Consultation.objects.get()
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        self.assertEqual(consultation.consultation_fee, Decimal("72.500"))
        self.assertEqual(consultation.doctor, self.doctor)
        self.assertEqual(consultation.blood_pressure, "120/80")
        self.assertEqual(consultation.temperature, "37.2")
        self.assertEqual(consultation.gad, "1.10")
        self.assertEqual(consultation.spo2, "98")
        self.assertEqual(consultation.heart_rate, "72")
        self.assertEqual(consultation.clinical_other, "Observation fictive")
        self.assertEqual(consultation.medical_act, "Examen clinique fictif")
        self.assertEqual(consultation.medical_conduct, "Conduite fictive")
        self.assertEqual(consultation.biological_exams, "Bilan sanguin fictif")
        self.assertEqual(consultation.imaging_exams, "Scanner fictif")
        self.assertEqual(consultation.complementary_exams, "Bilan sanguin fictif")
        self.assertEqual(consultation.destination, "Orientation personnalisée")

    def test_new_consultation_can_be_created_without_a_fee(self):
        response = self.client.post(
            reverse("consultations:create"),
            {
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Consultation sans prix",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            },
        )

        consultation = Consultation.objects.get()
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        self.assertIsNone(consultation.consultation_fee)

    def test_create_consultation_saves_unique_tags_as_separate_values(self):
        response = self.client.post(
            reverse("consultations:create"),
            {
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Douleur abdominale\nDouleur thoracique\ndouleur abdominale",
                "consultation_fee": "72.500",
                "medical_act": "Injection\nPansement\nInjection",
                "medical_conduct": "Surveillance\nContrôle clinique",
                "biological_exams": "NFS\nGlycémie\nglycemie",
                "imaging_exams": "Scanner\nÉchographie",
                "complementary_exams": "Bilan A\nBilan B",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            },
        )

        consultation = Consultation.objects.get()
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        self.assertEqual(
            consultation.reason,
            "Douleur abdominale\nDouleur thoracique",
        )
        self.assertEqual(consultation.medical_act, "Injection\nPansement")
        self.assertEqual(
            consultation.medical_conduct,
            "Surveillance\nContrôle clinique",
        )
        self.assertEqual(consultation.biological_exams, "NFS\nGlycémie")
        self.assertEqual(consultation.imaging_exams, "Scanner\nÉchographie")
        self.assertEqual(consultation.complementary_exams, "Bilan A\nBilan B")

    def test_edit_form_preserves_existing_tag_values(self):
        consultation = self.create_consultation(
            reason="Motif historique\nDeuxième motif",
            medical_act="Injection\nPansement",
            biological_exams="NFS\nGlycémie",
            imaging_exams="Scanner\nÉchographie",
        )

        response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )

        self.assertEqual(response.status_code, 200)
        for field_name, expected_value in (
            ("reason", "Motif historique\nDeuxième motif"),
            ("medical_act", "Injection\nPansement"),
            ("biological_exams", "NFS\nGlycémie"),
            ("imaging_exams", "Scanner\nÉchographie"),
        ):
            self.assertEqual(
                response.context["form"][field_name].value(),
                expected_value,
            )
        self.assertContains(response, 'data-tag-input=""')

    def test_edit_consultation_replaces_and_saves_tag_values(self):
        consultation = self.create_consultation(
            reason="Ancien motif",
            medical_act="Ancien acte",
            biological_exams="Ancien bilan",
        )

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": "Nouveau motif\nSecond motif",
                "consultation_fee": "100.000",
                "medical_act": "Injection\nPansement",
                "biological_exams": "NFS\nGlycémie",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertEqual(consultation.reason, "Nouveau motif\nSecond motif")
        self.assertEqual(consultation.medical_act, "Injection\nPansement")
        self.assertEqual(consultation.biological_exams, "NFS\nGlycémie")

    def test_consultation_form_has_optional_fee_and_clinical_sections(self):
        response = self.client.get(reverse("consultations:create"))
        content = response.content.decode()

        self.assertLess(
            content.index("Examen clinique"),
            content.index("Informations d’assurance"),
        )
        self.assertLess(
            content.index("Acte médical, conduite et examens"),
            content.index("Informations d’assurance"),
        )
        self.assertContains(response, "<h2>Prix de consultation (facultatif)</h2>")
        self.assertContains(response, "Vous pouvez laisser ce champ vide.")
        self.assertContains(response, "Scanner, échographie")
        self.assertContains(response, 'data-suggestion-category="reason"')
        self.assertContains(response, 'data-suggestion-category="imaging_exam"')
        self.assertContains(response, "Gérer les suggestions")

    def test_new_consultation_leaves_insurance_file_answer_unselected(self):
        response = self.client.get(reverse("consultations:create"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["insurance_file_filled"].value(),
            None,
        )
        choices = list(
            response.context["form"].fields["insurance_file_filled"].choices
        )
        self.assertEqual(choices, [("true", "Oui"), ("false", "Non")])
        self.assertNotContains(response, "Pas encore renseigné")

    def test_suggestion_api_matches_accents_and_scopes_personal_proposals(self):
        MedicalSuggestion.objects.create(
            doctor=self.doctor,
            category=MedicalSuggestion.Category.REASON,
            text="Douleur thoracique",
            usage_count=2,
        )
        shared = MedicalSuggestion.objects.get(
            doctor__isnull=True,
            category=MedicalSuggestion.Category.REASON,
            normalized_text="douleur abdominale",
        )
        shared.usage_count = 10
        shared.save(update_fields=["usage_count"])
        another_doctor = User.objects.create_user(
            username="other-doctor",
            password="suggestion-test-password",
            role=User.Role.DOCTOR,
        )
        MedicalSuggestion.objects.create(
            doctor=another_doctor,
            category=MedicalSuggestion.Category.REASON,
            text="Douleur lombaire privée",
            usage_count=50,
        )

        response = self.client.get(
            reverse("consultations:suggestions_api"),
            {"category": MedicalSuggestion.Category.REASON, "q": "Douléur"},
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        result_texts = [result["text"] for result in results]
        self.assertEqual(result_texts[:2], [shared.text, "Douleur thoracique"])
        self.assertNotIn("Douleur lombaire privée", result_texts)

    def test_blank_suggestion_search_returns_popular_limited_results(self):
        popular = MedicalSuggestion.objects.create(
            category=MedicalSuggestion.Category.IMAGING_EXAM,
            text="Imagerie populaire",
            usage_count=20,
        )

        response = self.client.get(
            reverse("consultations:suggestions_api"),
            {"category": MedicalSuggestion.Category.IMAGING_EXAM},
        )

        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        self.assertLessEqual(len(results), 8)
        self.assertEqual(results[0]["text"], popular.text)

    def test_selected_suggestion_usage_is_recorded(self):
        suggestion = MedicalSuggestion.objects.create(
            doctor=self.doctor,
            category=MedicalSuggestion.Category.REASON,
            text="Motif personnel",
        )

        response = self.client.post(
            reverse("consultations:suggestions_use", args=[suggestion.pk])
        )

        self.assertEqual(response.status_code, 204)
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.usage_count, 1)

    def test_doctor_can_create_edit_and_archive_personal_suggestions(self):
        response = self.client.post(
            reverse("consultations:suggestion_create"),
            {
                "category": MedicalSuggestion.Category.IMAGING_EXAM,
                "text": "Échographie ciblée",
            },
        )

        suggestion = MedicalSuggestion.objects.get(
            doctor=self.doctor,
            text="Échographie ciblée",
        )
        self.assertRedirects(response, reverse("consultations:suggestions"))

        response = self.client.post(
            reverse("consultations:suggestion_update", args=[suggestion.pk]),
            {
                "category": MedicalSuggestion.Category.IMAGING_EXAM,
                "text": "Échographie abdominale",
            },
        )
        self.assertRedirects(response, reverse("consultations:suggestions"))
        suggestion.refresh_from_db()
        self.assertEqual(suggestion.text, "Échographie abdominale")

        response = self.client.post(
            reverse("consultations:suggestion_archive", args=[suggestion.pk])
        )
        self.assertRedirects(response, reverse("consultations:suggestions"))
        suggestion.refresh_from_db()
        self.assertFalse(suggestion.is_active)

    def test_doctor_cannot_edit_shared_suggestion(self):
        suggestion = MedicalSuggestion.objects.create(
            category=MedicalSuggestion.Category.REASON,
            text="Suggestion partagée",
        )

        response = self.client.get(
            reverse("consultations:suggestion_update", args=[suggestion.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_insurance_declared_no_is_not_insured(self):
        form = ConsultationForm(
            data={
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Test",
                "consultation_fee": "50.000",
                "has_insurance": "false",
                "insurance_file_filled": "true",
                "insurance_type": "CNAM",
                "insurer": "Organisme fictif",
                "affiliation_number": "FICTIF-1",
                "insurance_comment": "Essai",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(form.cleaned_data["has_insurance"])
        self.assertFalse(form.cleaned_data["insurance_file_filled"])
        self.assertEqual(form.cleaned_data["insurance_type"], "")
        self.assertEqual(form.cleaned_data["insurer"], "")

    def test_unanswered_insurance_file_is_treated_as_not_filled(self):
        form = ConsultationForm(
            data={
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Test",
                "consultation_fee": "50.000",
                "has_insurance": "true",
                "insurance_file_filled": "",
                "insurance_type": "",
                "insurer": "",
                "affiliation_number": "",
                "insurance_comment": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["insurance_file_filled"])

    def test_unfilled_insurance_file_shows_not_filled_in_summary(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=False,
        )

        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.INCOMPLETE,
        )
        response = self.client.get(
            reverse("consultations:detail", args=[consultation.pk])
        )
        self.assertContains(response, "Non remplie")
        self.assertContains(response, "Dossier déclaré rempli")

    def test_uninsured_consultation_has_uninsured_status(self):
        consultation = self.create_consultation(
            has_insurance=False,
            insurance_file_filled=False,
        )

        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.NOT_INSURED,
        )
        response = self.client.get(
            reverse("consultations:detail", args=[consultation.pk])
        )
        self.assertContains(response, "Non assuré")

    def test_insured_but_unverified_consultation_is_incomplete(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-123",
        )

        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.INCOMPLETE,
        )

    def test_only_verified_and_complete_insurance_is_completed(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-123",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now(),
        )

        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.COMPLETED,
        )

    def test_verified_insurance_requires_all_administrative_fields(self):
        form = ConsultationForm(
            data={
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Test",
                "consultation_fee": "50.000",
                "has_insurance": "true",
                "insurance_file_filled": "true",
                "insurance_type": "CNAM",
                "insurer": "",
                "affiliation_number": "",
                "insurance_comment": "",
                "insurance_verified": "on",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("insurer", form.errors)
        self.assertIn("affiliation_number", form.errors)

    def test_creating_a_verified_insurance_records_verifying_doctor(self):
        response = self.client.post(
            reverse("consultations:create"),
            {
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "reason": "Consultation fictive",
                "consultation_fee": "80.000",
                "has_insurance": "true",
                "insurance_file_filled": "true",
                "insurance_type": Consultation.InsuranceType.CNAM,
                "insurer": "Organisme fictif",
                "affiliation_number": "FICTIF-456",
                "insurance_comment": "Dossier fictif vérifié",
                "insurance_verified": "on",
            },
        )

        consultation = Consultation.objects.get()
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        self.assertEqual(consultation.insurance_verified_by, self.doctor)
        self.assertIsNotNone(consultation.insurance_verified_at)
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.COMPLETED,
        )

    def test_consultation_history_shows_price_and_insurance_badges(self):
        consultation = self.create_consultation(has_insurance=True)

        response = self.client.get(
            reverse("patients:detail", args=[self.patient.pk])
        )

        self.assertContains(response, consultation.reference)
        self.assertContains(response, "—")
        self.assertContains(response, 'status-insurance-incomplete')

    def test_consultation_detail_shows_fee_and_insurance(self):
        consultation = self.create_consultation(
            consultation_fee=Decimal("100.000"),
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-789",
            blood_pressure="120/80",
            medical_act="Conduite fictive",
            complementary_exams="Scanner fictif",
            destination="Urgence",
        )
        response = self.client.get(
            reverse("consultations:detail", args=[consultation.pk])
        )

        self.assertContains(response, "100,000 TND")
        self.assertContains(response, "Organisme fictif")
        self.assertContains(response, "FICTIF-789")
        self.assertContains(response, "Non remplie")
        self.assertContains(response, "120/80")
        self.assertContains(response, "Conduite fictive")
        self.assertContains(response, "Scanner fictif")
        self.assertContains(response, "Urgence")

    def test_consultation_table_has_edit_and_confirmed_delete_actions(self):
        consultation = self.create_consultation()

        response = self.client.get(reverse("consultations:list"))

        self.assertContains(
            response,
            reverse("consultations:update", args=[consultation.pk]),
        )
        self.assertContains(
            response,
            reverse("consultations:delete", args=[consultation.pk]),
        )
        self.assertContains(response, "Supprimer définitivement cette consultation")

    def test_consultation_delete_requires_post_and_removes_only_consultation(self):
        consultation = self.create_consultation()
        delete_url = reverse("consultations:delete", args=[consultation.pk])

        response = self.client.get(delete_url)
        self.assertEqual(response.status_code, 405)
        self.assertTrue(Consultation.objects.filter(pk=consultation.pk).exists())

        response = self.client.post(delete_url)
        self.assertRedirects(response, reverse("consultations:list"))
        self.assertFalse(Consultation.objects.filter(pk=consultation.pk).exists())
        self.assertTrue(Patient.objects.filter(pk=self.patient.pk).exists())

    def test_consultation_details_are_read_only(self):
        consultation = self.create_consultation()

        response = self.client.post(
            reverse("consultations:detail", args=[consultation.pk]),
            {"reason": "Remplacement interdit"},
        )

        self.assertEqual(response.status_code, 405)
        consultation.refresh_from_db()
        self.assertEqual(consultation.reason, "Motif fictif de test")

    def test_edit_updates_consultation_and_optional_fee(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-ORIGINAL",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now() - timedelta(days=1),
        )
        new_date = timezone.localdate() - timedelta(days=1)

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": new_date.isoformat(),
                "reason": "Motif corrigé",
                "consultation_fee": "120.000",
                "blood_pressure": "130/85",
                "temperature": "38",
                "gad": "1.20",
                "spo2": "96",
                "heart_rate": "88",
                "clinical_other": "Nouvelle observation",
                "medical_act": "Nouveau geste",
                "medical_conduct": "Nouvelle conduite",
                "biological_exams": "NFS",
                "imaging_exams": "Échographie",
                "complementary_exams": "Échographie",
                "destination": "Orientation personnalisée",
                "has_insurance": "true",
                "insurance_file_filled": "true",
                "insurance_type": Consultation.InsuranceType.CNAM,
                "insurer": "Organisme fictif",
                "affiliation_number": "FICTIF-ORIGINAL",
                "insurance_comment": "Commentaire corrigé",
                "insurance_verified": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertEqual(consultation.reason, "Motif corrigé")
        self.assertEqual(consultation.consultation_date, new_date)
        self.assertEqual(consultation.blood_pressure, "130/85")
        self.assertEqual(consultation.temperature, "38")
        self.assertEqual(consultation.gad, "1.20")
        self.assertEqual(consultation.spo2, "96")
        self.assertEqual(consultation.heart_rate, "88")
        self.assertEqual(consultation.clinical_other, "Nouvelle observation")
        self.assertEqual(consultation.medical_act, "Nouveau geste")
        self.assertEqual(consultation.medical_conduct, "Nouvelle conduite")
        self.assertEqual(consultation.biological_exams, "NFS")
        self.assertEqual(consultation.imaging_exams, "Échographie")
        self.assertEqual(consultation.complementary_exams, "Échographie")
        self.assertEqual(consultation.destination, "Orientation personnalisée")
        self.assertEqual(consultation.consultation_fee, Decimal("120.000"))
        self.assertEqual(consultation.insurance_status, Consultation.InsuranceStatus.COMPLETED)
        self.assertEqual(consultation.insurance_verified_by, self.doctor)

    def test_edit_form_prefills_saved_date_and_consultation_information(self):
        consultation_date = timezone.localdate() - timedelta(days=2)
        consultation = self.create_consultation(
            consultation_date=consultation_date,
            reason="Douleur thoracique",
            blood_pressure="120/80",
            temperature="37.2",
            gad="1.10",
            spo2="98",
            heart_rate="72",
            clinical_other="Observation déjà saisie",
            medical_act="Acte déjà saisi",
            medical_conduct="Conduite déjà saisie",
            biological_exams="Bilan déjà saisi",
            imaging_exams="Imagerie déjà saisie",
            complementary_exams="Autre examen déjà saisi",
            destination="Orientation personnalisée",
            insurance_verified_at=timezone.now(),
        )

        response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            f'value="{consultation_date.isoformat()}"',
        )
        for saved_value in (
            "Douleur thoracique",
            "120/80",
            "37.2",
            "1.10",
            "98",
            "72",
            "Observation déjà saisie",
            "Acte déjà saisi",
            "Conduite déjà saisie",
            "Bilan déjà saisi",
            "Imagerie déjà saisie",
            "Autre examen déjà saisi",
            "Orientation personnalisée",
        ):
            self.assertContains(response, saved_value)
        self.assertTrue(response.context["form"]["insurance_verified"].value())

    def test_edit_form_prefills_saved_insurance_radio_values(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
        )

        response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["has_insurance"].value(),
            "true",
        )
        self.assertEqual(
            response.context["form"]["insurance_file_filled"].value(),
            "true",
        )

    def test_edit_form_shows_saved_no_for_unfilled_insurance_file(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=False,
        )

        response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["form"]["has_insurance"].value(),
            "true",
        )
        self.assertEqual(
            response.context["form"]["insurance_file_filled"].value(),
            "false",
        )

    def test_edit_preserves_unanswered_insurance_file_and_marks_it_unfilled(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=False,
        )
        consultation.insurance_file_filled = None
        consultation.save(update_fields=["insurance_file_filled"])

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": consultation.reason,
                "consultation_fee": "100.000",
                "has_insurance": "true",
                "insurance_file_filled": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertIsNone(consultation.insurance_file_filled)
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.INCOMPLETE,
        )

        response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )
        self.assertEqual(
            response.context["form"]["insurance_file_filled"].value(),
            None,
        )

    def test_editing_insurance_information_clears_previous_verification(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-ORIGINAL",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now(),
        )

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": consultation.reason,
                "consultation_fee": "100.000",
                "has_insurance": "true",
                "insurance_file_filled": "true",
                "insurance_type": Consultation.InsuranceType.CNAM,
                "insurer": "Nouvel organisme fictif",
                "affiliation_number": "FICTIF-NOUVEAU",
                "insurance_comment": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.INCOMPLETE,
        )
        self.assertIsNone(consultation.insurance_verified_by)
        self.assertIsNone(consultation.insurance_verified_at)

    def test_editing_insurance_to_no_persists_both_no_values(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-ORIGINAL",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now(),
        )

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": consultation.reason,
                "consultation_fee": "100.000",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertFalse(consultation.has_insurance)
        self.assertFalse(consultation.insurance_file_filled)
        self.assertEqual(consultation.insurance_type, "")
        self.assertEqual(consultation.insurer, "")
        self.assertEqual(consultation.affiliation_number, "")
        self.assertIsNone(consultation.insurance_verified_at)

    def test_editing_changed_insurance_and_reconfirming_updates_verifier(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-ORIGINAL",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now() - timedelta(days=1),
        )

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": self.patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": consultation.reason,
                "consultation_fee": "100.000",
                "has_insurance": "true",
                "insurance_file_filled": "true",
                "insurance_type": Consultation.InsuranceType.PRIVATE,
                "insurer": "Assureur fictif",
                "affiliation_number": "FICTIF-PRIVE",
                "insurance_comment": "",
                "insurance_verified": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.COMPLETED,
        )
        self.assertEqual(consultation.insurance_verified_by, self.doctor)
        self.assertGreater(
            consultation.insurance_verified_at,
            timezone.now() - timedelta(minutes=1),
        )

    def test_patient_association_is_immutable_when_editing_consultation(self):
        consultation = self.create_consultation()
        another_patient = Patient.objects.create(
            first_name="Autre",
            last_name="Patient fictif",
        )
        form_response = self.client.get(
            reverse("consultations:update", args=[consultation.pk])
        )
        self.assertContains(form_response, 'disabled')

        response = self.client.post(
            reverse("consultations:update", args=[consultation.pk]),
            {
                "patient": another_patient.pk,
                "consultation_date": consultation.consultation_date.isoformat(),
                "reason": "Motif mis à jour",
                "consultation_fee": "100.000",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            },
        )

        self.assertRedirects(
            response,
            reverse("consultations:detail", args=[consultation.pk]),
        )
        consultation.refresh_from_db()
        self.assertEqual(consultation.patient, self.patient)

    def test_inactive_user_cannot_view_consultations(self):
        self.client.logout()
        inactive_doctor = User.objects.create_user(
            username="inactive",
            password="test-password-only",
            role=User.Role.DOCTOR,
            is_active=False,
        )
        self.client.force_login(inactive_doctor)

        response = self.client.get(reverse("consultations:list"))

        self.assertRedirects(
            response,
            f"{reverse('core:login')}?next={reverse('consultations:list')}",
        )

    def test_insurance_status_is_derived_from_verified_information(self):
        consultation = self.create_consultation(
            has_insurance=True,
            insurance_file_filled=True,
            insurance_type=Consultation.InsuranceType.CNAM,
            insurer="Organisme fictif",
            affiliation_number="FICTIF-321",
            insurance_verified_by=self.doctor,
            insurance_verified_at=timezone.now(),
        )
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.COMPLETED,
        )

        consultation.insurance_file_filled = False
        consultation.insurance_verified_by = None
        consultation.insurance_verified_at = None
        self.assertEqual(
            consultation.insurance_status,
            Consultation.InsuranceStatus.INCOMPLETE,
        )

    def test_future_consultation_date_is_rejected(self):
        form = ConsultationForm(
            data={
                "patient": self.patient.pk,
                "consultation_date": (
                    timezone.localdate() + timedelta(days=1)
                ).isoformat(),
                "reason": "Test",
                "consultation_fee": "50.000",
                "has_insurance": "false",
                "insurance_file_filled": "false",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("consultation_date", form.errors)
