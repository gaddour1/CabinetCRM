from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Prescription(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        VALIDATED = "VALIDATED", "Validée"

    consultation = models.OneToOneField(
        "consultations.Consultation",
        on_delete=models.CASCADE,
        related_name="prescription",
        verbose_name="consultation",
    )
    prescriber = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prescriptions",
        verbose_name="médecin prescripteur",
    )
    status = models.CharField(
        "état",
        max_length=12,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    recommendations = models.TextField(
        "conseils et recommandations au patient",
        blank=True,
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    updated_at = models.DateTimeField("modifiée le", auto_now=True)
    validated_at = models.DateTimeField("validée le", blank=True, null=True)
    validated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="validated_prescriptions",
        verbose_name="validée par",
        blank=True,
        null=True,
    )

    class Meta:
        ordering = ["-created_at", "-pk"]
        verbose_name = "ordonnance médicale"
        verbose_name_plural = "ordonnances médicales"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(status="DRAFT", validated_at__isnull=True, validated_by__isnull=True)
                    | Q(
                        status="VALIDATED",
                        validated_at__isnull=False,
                        validated_by__isnull=False,
                    )
                ),
                name="prescription_status_validation_consistent",
            ),
        ]

    def __str__(self):
        return f"Ordonnance — {self.consultation.reference}"


class PrescribedMedication(models.Model):
    class PharmaceuticalForm(models.TextChoices):
        TABLET = "TABLET", "Comprimé"
        CAPSULE = "CAPSULE", "Gélule"
        SYRUP = "SYRUP", "Sirop"
        CREAM = "CREAM", "Crème"
        OINTMENT = "OINTMENT", "Pommade"
        INJECTION = "INJECTION", "Injection"
        DROPS = "DROPS", "Gouttes"
        OTHER = "OTHER", "Autre"

    class AdministrationRoute(models.TextChoices):
        ORAL = "ORAL", "Orale"
        CUTANEOUS = "CUTANEOUS", "Cutanée"
        OPHTHALMIC = "OPHTHALMIC", "Ophtalmique"
        NASAL = "NASAL", "Nasale"
        INJECTABLE = "INJECTABLE", "Injectable"
        OTHER = "OTHER", "Autre"

    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="medications",
        verbose_name="ordonnance",
    )
    position = models.PositiveIntegerField("ordre", default=0)
    name = models.CharField("nom du médicament", max_length=200)
    dosage = models.CharField("dosage", max_length=100, blank=True)
    pharmaceutical_form = models.CharField(
        "forme pharmaceutique",
        max_length=12,
        choices=PharmaceuticalForm.choices,
        blank=True,
    )
    administration_route = models.CharField(
        "voie d’administration",
        max_length=12,
        choices=AdministrationRoute.choices,
        blank=True,
    )
    posology = models.TextField("posologie")
    frequency = models.CharField("fréquence de prise", max_length=200)
    duration = models.CharField("durée du traitement", max_length=100)
    quantity = models.CharField("quantité prescrite", max_length=100, blank=True)
    instructions = models.TextField("instructions particulières", blank=True)

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = "médicament prescrit"
        verbose_name_plural = "médicaments prescrits"

    def __str__(self):
        return self.name


class MedicationLibraryEntry(models.Model):
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medication_library",
        verbose_name="médecin",
    )
    name = models.CharField("nom du médicament", max_length=200)
    dosage = models.CharField("dosage", max_length=100, blank=True)
    pharmaceutical_form = models.CharField(
        "forme pharmaceutique",
        max_length=12,
        choices=PrescribedMedication.PharmaceuticalForm.choices,
        blank=True,
    )
    administration_route = models.CharField(
        "voie d’administration",
        max_length=12,
        choices=PrescribedMedication.AdministrationRoute.choices,
        blank=True,
    )
    posology = models.TextField("posologie", blank=True)
    frequency = models.CharField("fréquence de prise", max_length=200, blank=True)
    duration = models.CharField("durée du traitement", max_length=100, blank=True)
    quantity = models.CharField("quantité prescrite", max_length=100, blank=True)
    instructions = models.TextField("instructions particulières", blank=True)
    created_at = models.DateTimeField("ajouté le", auto_now_add=True)

    class Meta:
        ordering = ["name", "dosage"]
        verbose_name = "médicament de la bibliothèque"
        verbose_name_plural = "bibliothèque personnelle de médicaments"
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "name", "dosage", "pharmaceutical_form"],
                name="unique_personal_medication_suggestion",
            ),
        ]

    def __str__(self):
        return f"{self.name} {self.dosage}".strip()


class PrescriptionRevision(models.Model):
    prescription = models.ForeignKey(
        Prescription,
        on_delete=models.CASCADE,
        related_name="revisions",
        verbose_name="ordonnance",
    )
    version_number = models.PositiveIntegerField("version précédente")
    snapshot = models.JSONField("contenu de la version précédente")
    reason = models.TextField("motif de la correction")
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="prescription_corrections",
        verbose_name="corrigée par",
    )
    created_at = models.DateTimeField("corrigée le", default=timezone.now)

    class Meta:
        ordering = ["-version_number"]
        verbose_name = "version antérieure d’ordonnance"
        verbose_name_plural = "historique des corrections d’ordonnance"
        constraints = [
            models.UniqueConstraint(
                fields=["prescription", "version_number"],
                name="unique_prescription_revision_number",
            ),
        ]

    def __str__(self):
        return f"{self.prescription} — version {self.version_number}"
