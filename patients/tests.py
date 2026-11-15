from datetime import date, timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from .forms import PatientForm
from .models import Patient


class PatientFormTests(TestCase):
    def test_rejects_future_birth_date(self):
        form = PatientForm(
            data={
                "first_name": "Patient",
                "last_name": "Fictif",
                "date_of_birth": (timezone.localdate() + timedelta(days=1)).isoformat(),
                "sex": "F",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("date_of_birth", form.errors)

    def test_normalizes_and_validates_blood_group(self):
        form = PatientForm(
            data={
                "first_name": "Patient",
                "last_name": "Fictif",
                "blood_group": "o+",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["blood_group"], "O+")


class PatientWorkflowTests(TestCase):
    def setUp(self):
        self.doctor = User.objects.create_user(
            username="doctor",
            password="test-password-only",
            role=User.Role.DOCTOR,
        )
        self.client.force_login(self.doctor)

    def test_create_patient_and_search_by_name_phone_or_cin(self):
        response = self.client.post(
            reverse("patients:create"),
            {
                "first_name": "Sana",
                "last_name": "Exemple",
                "cin": "00000000",
                "phone": "20000000",
                "sex": "F",
            },
        )

        patient = Patient.objects.get()
        self.assertRedirects(response, reverse("patients:detail", args=[patient.pk]))
        for query in ("Sana", "00000000", "20000000"):
            result = self.client.get(reverse("patients:list"), {"q": query})
            self.assertContains(result, "Sana Exemple")

    def test_search_by_birth_date_and_partial_sort(self):
        patient = Patient.objects.create(
            first_name="Nour",
            last_name="Exemple",
            date_of_birth=date(1990, 5, 12),
        )

        response = self.client.get(
            reverse("patients:list"),
            {"q": "12/05/1990", "sort": "birth_date", "partial": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)
        self.assertIn(patient.record_number, response.json()["rows"])

    def test_patient_list_sorts_by_first_name_in_requested_direction(self):
        Patient.objects.create(first_name="Zoe", last_name="Test")
        Patient.objects.create(first_name="Amine", last_name="Test")

        response = self.client.get(
            reverse("patients:list"),
            {"sort": "first_name", "direction": "asc", "partial": "1"},
        )

        rows = response.json()["rows"]
        self.assertLess(rows.index("Amine"), rows.index("Zoe"))

    def test_archive_preserves_record_and_can_be_restored(self):
        patient = Patient.objects.create(first_name="Nour", last_name="Test")

        response = self.client.post(
            reverse("patients:archive", args=[patient.pk])
        )

        patient.refresh_from_db()
        self.assertRedirects(response, reverse("patients:list"))
        self.assertTrue(patient.is_archived)
        self.assertEqual(Patient.objects.count(), 1)

        response = self.client.post(
            reverse("patients:restore", args=[patient.pk])
        )

        patient.refresh_from_db()
        self.assertRedirects(response, reverse("patients:detail", args=[patient.pk]))
        self.assertFalse(patient.is_archived)

    def test_archived_patient_is_hidden_from_active_list(self):
        patient = Patient.objects.create(first_name="Archive", last_name="Test")
        patient.archive()

        self.assertNotContains(
            self.client.get(reverse("patients:list")), "Archive Test"
        )
        self.assertContains(
            self.client.get(reverse("patients:list"), {"archives": "1"}),
            "Archive Test",
        )
