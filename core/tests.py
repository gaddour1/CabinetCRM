import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class InitialDoctorSetupTests(TestCase):
    def test_setup_check_reports_missing_initial_doctor(self):
        output = StringIO()

        call_command("initialize_clinic_doctor", check=True, stdout=output)

        self.assertIn("CABINET_DOCTOR_REQUIRED=1", output.getvalue())

    def test_setup_creates_doctor_without_putting_password_in_output(self):
        password = "Long!Private-Setup-Password-2026"
        output = StringIO()

        with patch(
            "core.management.commands.initialize_clinic_doctor.sys.stdin",
            StringIO(
                json.dumps(
                    {
                        "username": "doctor",
                        "first_name": "Médecin",
                        "last_name": "Exemple",
                        "password": password,
                    }
                )
            ),
        ):
            call_command("initialize_clinic_doctor", stdout=output)

        doctor = User.objects.get(username="doctor")
        self.assertEqual(doctor.role, User.Role.DOCTOR)
        self.assertTrue(doctor.check_password(password))
        self.assertNotIn(password, output.getvalue())
        self.assertIn("CABINET_DOCTOR_REQUIRED=0", self._check_output())

    def test_setup_rejects_weak_password_and_never_creates_a_user(self):
        with self.assertRaises(CommandError):
            with patch(
                "core.management.commands.initialize_clinic_doctor.sys.stdin",
                StringIO(
                    json.dumps(
                        {
                            "username": "doctor",
                            "password": "password",
                        }
                    )
                ),
            ):
                call_command("initialize_clinic_doctor", stdout=StringIO())

        self.assertFalse(User.objects.exists())

    def _check_output(self):
        output = StringIO()
        call_command("initialize_clinic_doctor", check=True, stdout=output)
        return output.getvalue()


class DoctorDashboardTests(TestCase):
    def test_dashboard_redirects_unauthenticated_user_to_login(self):
        response = self.client.get(reverse("core:dashboard"))

        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:dashboard')}"
        )

    def test_doctor_can_open_dashboard_and_patient_module(self):
        User.objects.create_user(
            username="doctor",
            password="test-password-only",
            role=User.Role.DOCTOR,
        )
        self.client.login(username="doctor", password="test-password-only")

        self.assertEqual(self.client.get(reverse("core:dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("patients:list")).status_code, 200)

    def test_inactive_user_cannot_open_dashboard(self):
        User.objects.create_user(
            username="inactive",
            password="test-password-only",
            is_active=False,
        )

        response = self.client.get(reverse("core:dashboard"))

        self.assertRedirects(
            response, f"{reverse('core:login')}?next={reverse('core:dashboard')}"
        )

    def test_non_medical_account_is_denied_from_patient_module(self):
        user = User.objects.create_user(
            username="other",
            password="test-password-only",
            role="OTHER",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("patients:list"))

        self.assertEqual(response.status_code, 403)
