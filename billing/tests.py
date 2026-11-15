from decimal import Decimal

from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class V1BillingDataMigrationTests(TransactionTestCase):
    migrate_from = [
        ("billing", "0001_initial"),
        ("consultations", "0005_alter_consultation_reason"),
    ]
    migrate_to = [
        ("billing", "0002_remove_payment_invoice_remove_payment_created_by_and_more"),
        ("consultations", "0006_optional_consultation_fee"),
        ("prescriptions", "0001_initial"),
    ]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        User = old_apps.get_model("accounts", "User")
        Patient = old_apps.get_model("patients", "Patient")
        Consultation = old_apps.get_model("consultations", "Consultation")
        Invoice = old_apps.get_model("billing", "Invoice")
        Payment = old_apps.get_model("billing", "Payment")

        doctor = User.objects.create(
            username="migration-test-doctor",
            password="not-a-real-password",
            is_staff=True,
        )
        self.expected = []
        for index, payments in enumerate(
            ((Decimal("35.000"), Decimal("65.000")), (Decimal("20.000"),)),
            start=1,
        ):
            patient = Patient.objects.create(
                first_name=f"Patient fictif {index}",
                last_name="Migration V1",
            )
            invoice = Invoice.objects.create(
                number=f"TEST-V1-INVOICE-{index}",
                patient_id=patient.pk,
                consultation_fee=Decimal("100.000"),
                created_by_id=doctor.pk,
                notes="Donnée synthétique pour test de migration",
            )
            consultation = Consultation.objects.create(
                patient_id=patient.pk,
                doctor_id=doctor.pk,
                invoice_id=invoice.pk,
                reason="Consultation fictive de migration",
            )
            payment_ids = []
            for payment_index, amount in enumerate(payments, start=1):
                payment = Payment.objects.create(
                    invoice_id=invoice.pk,
                    amount=amount,
                    method="CASH",
                    reference=f"TEST-{index}-{payment_index}",
                    created_by_id=doctor.pk,
                )
                payment_ids.append(payment.pk)
            self.expected.append(
                {
                    "patient_id": patient.pk,
                    "consultation_id": consultation.pk,
                    "invoice_id": invoice.pk,
                    "payment_ids": payment_ids,
                    "paid": sum(payments),
                }
            )

        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_v1_patients_consultations_invoices_and_payments_survive_v2(self):
        from consultations.models import Consultation
        from patients.models import Patient

        self.assertEqual(Patient.objects.count(), 2)
        self.assertEqual(Consultation.objects.count(), 2)
        self.assertEqual(
            list(
                Consultation.objects.order_by("pk").values_list(
                    "consultation_fee", flat=True
                )
            ),
            [Decimal("100.000"), Decimal("100.000")],
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, patient_id, consultation_fee "
                "FROM billing_invoice ORDER BY id"
            )
            invoices = cursor.fetchall()
            cursor.execute(
                "SELECT id, invoice_id, amount, created_by_id "
                "FROM billing_payment ORDER BY id"
            )
            payments = cursor.fetchall()
            cursor.execute(
                "SELECT id, patient_id FROM consultations_consultation ORDER BY id"
            )
            consultations = cursor.fetchall()

        self.assertEqual(len(invoices), 2)
        self.assertEqual(len(payments), 3)
        for expected, invoice, consultation in zip(
            self.expected,
            invoices,
            consultations,
            strict=True,
        ):
            self.assertEqual(invoice[0], expected["invoice_id"])
            self.assertEqual(invoice[1], expected["patient_id"])
            self.assertEqual(Decimal(invoice[2]), Decimal("100.000"))
            self.assertEqual(consultation[0], expected["consultation_id"])
            self.assertEqual(consultation[1], expected["patient_id"])

        for expected in self.expected:
            related_payments = [
                payment for payment in payments if payment[1] == expected["invoice_id"]
            ]
            self.assertEqual(
                {payment[0] for payment in related_payments},
                set(expected["payment_ids"]),
            )
            self.assertEqual(
                sum(Decimal(payment[2]) for payment in related_payments),
                expected["paid"],
            )
            self.assertTrue(all(payment[3] is not None for payment in related_payments))

    def _fixture_teardown(self):
        call_command(
            "flush",
            database=connection.alias,
            verbosity=0,
            interactive=False,
            reset_sequences=False,
            allow_cascade=True,
            inhibit_post_migrate=True,
        )
