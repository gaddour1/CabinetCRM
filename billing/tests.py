from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from patients.models import Patient

from .models import Invoice, Payment
from .services import record_payment


class BillingWorkflowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username="doctor",
            password="test-password-only",
            role=User.Role.DOCTOR,
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
        self.client.force_login(self.doctor)

    def pay(self, amount, method=Payment.Method.CASH):
        return record_payment(
            invoice_id=self.invoice.pk,
            amount=Decimal(amount),
            method=method,
            paid_at=timezone.now(),
            created_by=self.doctor,
        )

    def test_invoice_starts_unpaid_with_full_balance(self):
        self.assertEqual(self.invoice.amount_paid, Decimal("0.000"))
        self.assertEqual(self.invoice.remaining_amount, Decimal("100.000"))
        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.UNPAID,
        )

    def test_invoice_list_searches_payment_reference_without_changing_totals(self):
        record_payment(
            invoice_id=self.invoice.pk,
            amount=Decimal("25.000"),
            method=Payment.Method.CASH,
            paid_at=timezone.now(),
            created_by=self.doctor,
            reference="PAYREF-TEST-42",
        )

        response = self.client.get(
            reverse("billing:invoice_list"),
            {"q": "PAYREF-TEST-42", "partial": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertIn("25,000", response.json()["rows"])

    def test_invoice_list_accepts_sort_options_and_partial_results(self):
        response = self.client.get(
            reverse("billing:invoice_list"),
            {"sort": "patient", "direction": "asc", "partial": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertContains(response, self.invoice.number)

    def test_invoice_list_sorts_by_paid_amount(self):
        paid_invoice = Invoice.objects.create(
            patient=self.patient,
            consultation_fee=Decimal("100.000"),
            created_by=self.doctor,
        )
        record_payment(
            invoice_id=paid_invoice.pk,
            amount=Decimal("50.000"),
            method=Payment.Method.CASH,
            paid_at=timezone.now(),
            created_by=self.doctor,
        )

        response = self.client.get(
            reverse("billing:invoice_list"),
            {"sort": "paid", "direction": "desc", "partial": "1"},
        )

        rows = response.json()["rows"]
        self.assertLess(rows.index(paid_invoice.number), rows.index(self.invoice.number))

    def test_future_due_date_marks_unpaid_invoice_as_deferred(self):
        self.invoice.due_date = timezone.localdate() + timedelta(days=5)

        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.DEFERRED,
        )

    def test_partial_payment_tracks_balance_and_method(self):
        payment = self.pay("35.500", Payment.Method.TRANSFER)
        self.invoice.refresh_from_db()

        self.assertEqual(payment.get_method_display(), "Virement")
        self.assertEqual(self.invoice.amount_paid, Decimal("35.500"))
        self.assertEqual(self.invoice.remaining_amount, Decimal("64.500"))
        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.PARTIAL,
        )

    def test_exact_balance_payment_marks_invoice_paid(self):
        self.pay("40.000")
        self.pay("60.000", Payment.Method.CARD)
        self.invoice.refresh_from_db()

        self.assertEqual(self.invoice.amount_paid, Decimal("100.000"))
        self.assertEqual(self.invoice.remaining_amount, Decimal("0.000"))
        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.PAID,
        )

    def test_overpayment_is_rejected_without_recording_payment(self):
        self.pay("60.000")

        with self.assertRaises(ValidationError):
            self.pay("40.001")

        self.assertEqual(self.invoice.payments.count(), 1)

    def test_overdue_unpaid_invoice_is_marked_overdue(self):
        self.invoice.due_date = timezone.localdate() - timedelta(days=1)

        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.OVERDUE,
        )

    def test_partial_balance_past_due_is_marked_overdue(self):
        self.pay("10.000")
        self.invoice.due_date = timezone.localdate() - timedelta(days=1)

        self.assertEqual(
            self.invoice.financial_status,
            Invoice.FinancialStatus.OVERDUE,
        )

    def test_create_invoice_from_patient_page(self):
        response = self.client.post(
            reverse("billing:invoice_create"),
            {
                "patient": self.patient.pk,
                "consultation_date": timezone.localdate().isoformat(),
                "consultation_fee": "42.500",
                "due_date": "",
                "notes": "",
            },
        )

        created_invoice = Invoice.objects.get(consultation_fee=Decimal("42.500"))
        self.assertRedirects(
            response,
            reverse("billing:invoice_detail", args=[created_invoice.pk]),
        )
        self.assertEqual(created_invoice.created_by, self.doctor)

    def test_payment_submission_records_date_and_method(self):
        paid_at = timezone.localtime().strftime("%Y-%m-%dT%H:%M")
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.pk]),
            {
                "amount": "25.000",
                "method": Payment.Method.CHEQUE,
                "paid_at": paid_at,
                "reference": "CHQ-ESSAI",
                "notes": "Paiement fictif",
            },
        )

        self.assertRedirects(
            response,
            reverse("billing:invoice_detail", args=[self.invoice.pk]),
        )
        payment = self.invoice.payments.get()
        self.assertEqual(payment.amount, Decimal("25.000"))
        self.assertEqual(payment.method, Payment.Method.CHEQUE)
        self.assertEqual(payment.reference, "CHQ-ESSAI")
        self.assertEqual(payment.created_by, self.doctor)

    def test_payment_submission_rejects_amount_above_remaining_balance(self):
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.pk]),
            {
                "amount": "100.001",
                "method": Payment.Method.CASH,
                "paid_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "reference": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.invoice.payments.count(), 0)
        self.assertContains(response, "dépasse le solde restant")

    def test_payment_submission_rejects_future_payment_date(self):
        future = timezone.localtime() + timedelta(days=1)
        response = self.client.post(
            reverse("billing:invoice_detail", args=[self.invoice.pk]),
            {
                "amount": "10.000",
                "method": Payment.Method.CASH,
                "paid_at": future.strftime("%Y-%m-%dT%H:%M"),
                "reference": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.invoice.payments.count(), 0)
        self.assertContains(response, "ne peut pas être dans le futur")

    def test_payment_history_is_shown_on_patient_record(self):
        self.pay("20.000")

        response = self.client.get(
            reverse("patients:detail", args=[self.patient.pk])
        )

        self.assertContains(response, self.invoice.number)
        self.assertContains(response, "20,000 TND")
        self.assertContains(response, "80,000 TND")

    def test_billing_routes_require_authenticated_doctor(self):
        self.client.logout()

        response = self.client.get(reverse("billing:invoice_list"))

        self.assertRedirects(
            response,
            f"{reverse('core:login')}?next={reverse('billing:invoice_list')}",
        )

    def test_archived_patient_is_not_available_for_new_invoice(self):
        self.patient.archive()
        response = self.client.get(
            reverse("billing:invoice_create"),
            {"patient": self.patient.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Patient")
        self.assertNotContains(response, "Fictif")
