import uuid

from django.db import models
from django.utils import timezone


def generate_record_number():
    return f"PAT-{uuid.uuid4().hex[:12].upper()}"


class Patient(models.Model):
    class Sex(models.TextChoices):
        FEMALE = "F", "Femme"
        MALE = "M", "Homme"
        OTHER = "X", "Autre"

    record_number = models.CharField(
        "numéro de dossier",
        max_length=16,
        unique=True,
        default=generate_record_number,
        editable=False,
    )
    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    date_of_birth = models.DateField("date de naissance", blank=True, null=True)
    sex = models.CharField("sexe", max_length=1, choices=Sex.choices, blank=True)
    cin = models.CharField("CIN", max_length=20, blank=True, db_index=True)
    phone = models.CharField("téléphone", max_length=30, blank=True, db_index=True)
    address = models.TextField("adresse", blank=True)
    profession = models.CharField("profession", max_length=100, blank=True)
    blood_group = models.CharField("groupe sanguin", max_length=3, blank=True)
    medical_history = models.TextField("antécédents médicaux", blank=True)
    allergies = models.TextField("allergies", blank=True)
    usual_treatments = models.TextField("traitements habituels", blank=True)
    created_at = models.DateTimeField("créé le", auto_now_add=True)
    updated_at = models.DateTimeField("modifié le", auto_now=True)
    archived_at = models.DateTimeField("archivé le", blank=True, null=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        verbose_name = "patient"
        verbose_name_plural = "patients"
        permissions = [
            ("view_medical_details", "Peut consulter les informations médicales"),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def is_archived(self):
        return self.archived_at is not None

    def archive(self):
        if self.archived_at is None:
            self.archived_at = timezone.now()
            self.save(update_fields=["archived_at", "updated_at"])

    def restore(self):
        if self.archived_at is not None:
            self.archived_at = None
            self.save(update_fields=["archived_at", "updated_at"])
