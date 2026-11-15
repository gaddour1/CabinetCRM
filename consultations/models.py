import uuid
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from billing.models import Invoice, Payment
from patients.models import Patient


def generate_consultation_reference():
    return f"CONS-{uuid.uuid4().hex[:12].upper()}"


class Consultation(models.Model):
    class PaymentStatus(models.TextChoices):
        UNPAID = "UNPAID", "Non payé"
        PARTIAL = "PARTIAL", "Partiellement payé"
        PAID = "PAID", "Payé"

    class InsuranceStatus(models.TextChoices):
        COMPLETED = "COMPLETED", "Remplie"
        INCOMPLETE = "INCOMPLETE", "Non remplie"
        NOT_INSURED = "NOT_INSURED", "Non assuré"

    class InsuranceType(models.TextChoices):
        CNAM = "CNAM", "CNAM"
        PRIVATE = "PRIVATE", "Assurance privée"
        MUTUAL = "MUTUAL", "Mutuelle"
        OTHER = "OTHER", "Autre"

    class Destination(models.TextChoices):
        EMERGENCY = "EMERGENCY", "Urgence"
        SPECIALIST = "SPECIALIST", "Médecin spécialiste"
        HOME = "HOME", "Orientation à domicile"

    reference = models.CharField(
        "référence",
        max_length=17,
        unique=True,
        default=generate_consultation_reference,
        editable=False,
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="consultations",
        verbose_name="patient",
    )
    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consultations",
        verbose_name="médecin",
    )
    invoice = models.OneToOneField(
        Invoice,
        on_delete=models.PROTECT,
        related_name="consultation",
        verbose_name="facture",
    )
    consultation_date = models.DateField(
        "date de consultation",
        default=timezone.localdate,
    )
    reason = models.TextField("motif")
    blood_pressure = models.CharField("TA (mmHg)", max_length=30, blank=True)
    temperature = models.CharField("Température (°C)", max_length=30, blank=True)
    gad = models.CharField("GAD", max_length=50, blank=True)
    spo2 = models.CharField("SpO2 (%)", max_length=30, blank=True)
    heart_rate = models.CharField("FC (bpm)", max_length=30, blank=True)
    clinical_other = models.TextField("Autres observations cliniques", blank=True)
    medical_act = models.TextField("Acte médical", blank=True)
    medical_conduct = models.TextField("Conduite à tenir", blank=True)
    biological_exams = models.TextField("Examens biologiques", blank=True)
    imaging_exams = models.TextField("Examens d’imagerie", blank=True)
    complementary_exams = models.TextField(
        "Autres examens complémentaires (saisie antérieure)", blank=True
    )
    destination = models.CharField(
        "Destination du malade",
        max_length=250,
        blank=True,
    )
    has_insurance = models.BooleanField(
        "le patient possède une assurance",
        default=False,
    )
    insurance_file_filled = models.BooleanField(
        "le dossier d’assurance est déclaré rempli",
        default=False,
        blank=True,
        null=True,
    )
    insurance_type = models.CharField(
        "type d’assurance",
        max_length=10,
        choices=InsuranceType.choices,
        blank=True,
    )
    insurer = models.CharField("organisme assureur", max_length=150, blank=True)
    affiliation_number = models.CharField(
        "numéro d’affiliation",
        max_length=100,
        blank=True,
    )
    insurance_comment = models.TextField("commentaire d’assurance", blank=True)
    insurance_verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="verified_consultation_insurances",
        verbose_name="assurance vérifiée par",
        blank=True,
        null=True,
    )
    insurance_verified_at = models.DateTimeField(
        "assurance vérifiée le",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)

    class Meta:
        ordering = ["-consultation_date", "-created_at"]
        verbose_name = "consultation"
        verbose_name_plural = "consultations"

    def __str__(self):
        return f"{self.reference} — {self.patient}"

    def clean(self):
        super().clean()
        if self.invoice_id and self.patient_id:
            if self.invoice.patient_id != self.patient_id:
                raise ValidationError(
                    {"invoice": "La facture doit appartenir au patient de la consultation."}
                )

    @property
    def consultation_fee(self):
        return self.invoice.consultation_fee

    @property
    def amount_paid(self):
        annotated_total = getattr(self, "paid_total", None)
        if annotated_total is not None:
            return annotated_total
        return self.invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal(
            "0.000"
        )

    @property
    def remaining_amount(self):
        return self.consultation_fee - self.amount_paid

    @property
    def payment_status(self):
        if self.remaining_amount <= 0:
            return self.PaymentStatus.PAID
        if self.amount_paid > 0:
            return self.PaymentStatus.PARTIAL
        return self.PaymentStatus.UNPAID

    @property
    def payment_status_display(self):
        return self.PaymentStatus(self.payment_status).label

    @property
    def insurance_status(self):
        if not self.has_insurance:
            return self.InsuranceStatus.NOT_INSURED
        if (
            self.insurance_file_filled
            and self.insurance_type
            and self.insurer.strip()
            and self.affiliation_number.strip()
            and self.insurance_verified_by_id
            and self.insurance_verified_at
        ):
            return self.InsuranceStatus.COMPLETED
        return self.InsuranceStatus.INCOMPLETE

    @property
    def insurance_status_display(self):
        return self.InsuranceStatus(self.insurance_status).label

    @property
    def payment_methods(self):
        methods = dict(Payment.Method.choices)
        return [
            methods[method]
            for method in self.invoice.payments.order_by()
            .values_list("method", flat=True)
            .distinct()
        ]


def normalize_suggestion_text(value):
    decomposed = unicodedata.normalize("NFKD", value)
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_accents.casefold().strip()


class MedicalSuggestion(models.Model):
    class Category(models.TextChoices):
        REASON = "reason", "Motif de consultation"
        MEDICAL_ACT = "medical_act", "Acte médical"
        MEDICAL_CONDUCT = "medical_conduct", "Conduite à tenir"
        BIOLOGICAL_EXAM = "biological_exam", "Examen biologique"
        IMAGING_EXAM = "imaging_exam", "Examen d’imagerie"
        COMPLEMENTARY_EXAM = "complementary_exam", "Autre examen complémentaire"
        DESTINATION = "destination", "Destination du patient"

    doctor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="medical_suggestions",
        verbose_name="médecin propriétaire",
        blank=True,
        null=True,
    )
    category = models.CharField(
        "catégorie",
        max_length=30,
        choices=Category.choices,
    )
    text = models.CharField("proposition", max_length=250)
    normalized_text = models.CharField(
        "texte normalisé",
        max_length=250,
        editable=False,
    )
    is_active = models.BooleanField("active", default=True)
    usage_count = models.PositiveIntegerField("utilisations", default=0)
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    updated_at = models.DateTimeField("modifiée le", auto_now=True)

    class Meta:
        ordering = ["category", "-usage_count", "text"]
        verbose_name = "suggestion médicale"
        verbose_name_plural = "suggestions médicales"
        indexes = [
            models.Index(
                fields=["category", "is_active", "doctor"],
                name="med_sugg_category_active_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "doctor", "normalized_text"],
                condition=models.Q(doctor__isnull=False),
                name="unique_personal_med_suggestion",
            ),
            models.UniqueConstraint(
                fields=["category", "normalized_text"],
                condition=models.Q(doctor__isnull=True),
                name="unique_shared_med_suggestion",
            ),
        ]

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        self.normalized_text = normalize_suggestion_text(self.text)
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                "normalized_text",
                "updated_at",
            }
        super().save(*args, **kwargs)
