from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from consultations.models import Consultation
from patients.models import Patient


class DocumentViewsTests(TestCase):
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
            cin="00000000",
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            reason="Motif fictif de test",
            medical_act="Acte fictif de test",
            medical_conduct="Conduite fictive de test",
            biological_exams="Bilan fictif",
            imaging_exams="Imagerie fictive",
            destination="Orientation fictive",
        )
        self.client.force_login(self.doctor)

    def test_document_previews_show_existing_information(self):
        pages = (
            (
                reverse("documents:patient_sheet", args=[self.patient.pk]),
                ("Patient Fictif", "Motif fictif de test", "Non renseigné"),
            ),
            (
                reverse(
                    "documents:consultation_report",
                    args=[self.consultation.pk],
                ),
                ("Motif fictif de test", "Acte fictif de test", "Non renseigné"),
            ),
        )

        for url, expected_text in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response["Content-Type"].startswith("text/html"))
                for text in expected_text:
                    self.assertContains(response, text)

    def test_pdf_downloads_return_pdf_and_safe_filenames(self):
        documents = (
            (
                reverse("documents:patient_sheet", args=[self.patient.pk]),
                f"fiche-patient-{self.patient.record_number}.pdf",
            ),
            (
                reverse(
                    "documents:consultation_report",
                    args=[self.consultation.pk],
                ),
                f"compte-rendu-{self.consultation.reference}.pdf",
            ),
        )

        for url, filename in documents:
            with self.subTest(url=url):
                response = self.client.get(url, {"download": "1"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response["Content-Type"], "application/pdf")
                self.assertEqual(
                    response["Content-Disposition"],
                    f'attachment; filename="{filename}"',
                )
                self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_documents_do_not_modify_medical_records(self):
        before = (
            self.patient.first_name,
            self.patient.last_name,
            self.patient.cin,
            self.consultation.reason,
            self.consultation.medical_act,
        )
        document_urls = (
            reverse("documents:patient_sheet", args=[self.patient.pk]),
            reverse(
                "documents:consultation_report",
                args=[self.consultation.pk],
            ),
        )
        for url in document_urls:
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(
                self.client.get(url, {"download": "1"}).status_code,
                200,
            )

        self.patient.refresh_from_db()
        self.consultation.refresh_from_db()
        after = (
            self.patient.first_name,
            self.patient.last_name,
            self.patient.cin,
            self.consultation.reason,
            self.consultation.medical_act,
        )
        self.assertEqual(after, before)

    def test_documents_require_the_existing_medical_record_permission(self):
        inactive_doctor = User.objects.create_user(
            username="inactive-doctor",
            password="test-password",
            role="",
        )
        self.client.force_login(inactive_doctor)

        document_urls = (
            reverse("documents:patient_sheet", args=[self.patient.pk]),
            reverse(
                "documents:consultation_report",
                args=[self.consultation.pk],
            ),
        )

        for url in document_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_billing_document_routes_are_removed(self):
        response = self.client.get("/documents/factures/1/")
        self.assertEqual(response.status_code, 404)
