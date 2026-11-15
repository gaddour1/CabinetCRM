from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from billing.models import Invoice, Payment
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
        self.invoice = Invoice.objects.create(
            patient=self.patient,
            consultation_fee=Decimal("100.000"),
            created_by=self.doctor,
        )
        self.consultation = Consultation.objects.create(
            patient=self.patient,
            doctor=self.doctor,
            invoice=self.invoice,
            reason="Motif fictif de test",
            medical_act="Acte fictif de test",
            medical_conduct="Conduite fictive de test",
            biological_exams="Bilan fictif",
            imaging_exams="Imagerie fictive",
            destination="Orientation fictive",
        )
        self.payment = Payment.objects.create(
            invoice=self.invoice,
            amount=Decimal("25.000"),
            method=Payment.Method.CASH,
            paid_at=timezone.now(),
            reference="TEST-REC-01",
            created_by=self.doctor,
        )
        self.client.force_login(self.doctor)

    def test_document_previews_show_existing_information_and_empty_fields(self):
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
            (
                reverse("documents:invoice", args=[self.invoice.pk]),
                (
                    "100,000 TND",
                    "25,000 TND",
                    "75,000 TND",
                    "Partiellement réglée",
                ),
            ),
            (
                reverse("documents:payment_receipt", args=[self.payment.pk]),
                (
                    "25,000 TND",
                    "75,000 TND",
                    "Partiellement réglée",
                    "Non renseigné",
                ),
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
            (
                reverse("documents:invoice", args=[self.invoice.pk]),
                f"facture-{self.invoice.number}.pdf",
            ),
            (
                reverse("documents:payment_receipt", args=[self.payment.pk]),
                f"recu-REC-{timezone.localdate().year}-{self.payment.pk:05d}.pdf",
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

    def test_documents_do_not_modify_medical_or_financial_records(self):
        before = {
            "patient": (
                self.patient.first_name,
                self.patient.last_name,
                self.patient.cin,
            ),
            "consultation": (
                self.consultation.reason,
                self.consultation.medical_act,
                self.consultation.destination,
            ),
            "invoice": (
                self.invoice.consultation_fee,
                self.invoice.amount_paid,
                self.invoice.remaining_amount,
                self.invoice.financial_status,
            ),
            "payment": (
                self.payment.amount,
                self.payment.reference,
                self.payment.paid_at,
            ),
        }
        document_urls = (
            reverse("documents:patient_sheet", args=[self.patient.pk]),
            reverse(
                "documents:consultation_report",
                args=[self.consultation.pk],
            ),
            reverse("documents:invoice", args=[self.invoice.pk]),
            reverse("documents:payment_receipt", args=[self.payment.pk]),
        )
        for url in document_urls:
            self.assertEqual(self.client.get(url).status_code, 200)
            self.assertEqual(
                self.client.get(url, {"download": "1"}).status_code,
                200,
            )

        self.patient.refresh_from_db()
        self.consultation.refresh_from_db()
        self.invoice.refresh_from_db()
        self.payment.refresh_from_db()
        after = {
            "patient": (
                self.patient.first_name,
                self.patient.last_name,
                self.patient.cin,
            ),
            "consultation": (
                self.consultation.reason,
                self.consultation.medical_act,
                self.consultation.destination,
            ),
            "invoice": (
                self.invoice.consultation_fee,
                self.invoice.amount_paid,
                self.invoice.remaining_amount,
                self.invoice.financial_status,
            ),
            "payment": (
                self.payment.amount,
                self.payment.reference,
                self.payment.paid_at,
            ),
        }
        self.assertEqual(after, before)

    def test_documents_use_the_existing_medical_record_permission(self):
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
            reverse("documents:invoice", args=[self.invoice.pk]),
            reverse("documents:payment_receipt", args=[self.payment.pk]),
        )

        for url in document_urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_historical_invoice_without_consultation_can_be_printed(self):
        historical_invoice = Invoice.objects.create(
            patient=self.patient,
            consultation_fee=Decimal("45.000"),
            created_by=self.doctor,
        )

        response = self.client.get(
            reverse("documents:invoice", args=[historical_invoice.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, historical_invoice.number)
        self.assertContains(response, "45,000 TND")
