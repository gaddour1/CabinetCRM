from django.test import TestCase

from .models import User


class UserRoleTests(TestCase):
    def test_superuser_is_created_as_clinic_admin(self):
        admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.test",
            password="test-password-only",
        )

        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.can_manage_clinic)
        self.assertTrue(admin.can_access_medical_records)

    def test_doctor_can_access_records_but_cannot_manage_clinic(self):
        doctor = User.objects.create_user(
            username="docteur",
            password="test-password-only",
            role=User.Role.DOCTOR,
        )

        self.assertTrue(doctor.can_access_medical_records)
        self.assertFalse(doctor.can_manage_clinic)

    def test_inactive_users_have_no_clinic_access(self):
        doctor = User.objects.create_user(
            username="ancien",
            password="test-password-only",
            is_active=False,
        )

        self.assertFalse(doctor.can_access_medical_records)
        self.assertFalse(doctor.can_manage_clinic)
