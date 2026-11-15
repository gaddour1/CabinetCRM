from django.contrib.auth.models import AbstractUser
from django.db import models

from .managers import UserManager


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Administrateur"
        DOCTOR = "DOCTOR", "Médecin"

    role = models.CharField(
        "rôle au cabinet",
        max_length=10,
        choices=Role.choices,
        default=Role.DOCTOR,
    )

    objects = UserManager()

    class Meta:
        verbose_name = "utilisateur"
        verbose_name_plural = "utilisateurs"
        permissions = [
            ("manage_clinic_users", "Peut gérer les comptes du cabinet"),
            ("access_medical_records", "Peut accéder aux dossiers médicaux"),
        ]

    @property
    def can_manage_clinic(self):
        return self.is_active and self.role == self.Role.ADMIN

    @property
    def can_access_medical_records(self):
        return self.is_active and self.role in {self.Role.ADMIN, self.Role.DOCTOR}
