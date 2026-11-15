import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum
from django.utils import timezone

from patients.models import Patient


class Invoice(models.Model):
    class FinancialStatus(models.TextChoices):
        UNPAID = "UNPAID", "Non réglée"
        DEFERRED = "DEFERRED", "Paiement différé"
        PARTIAL = "PARTIAL", "Partiellement réglée"
        PAID = "PAID", "Réglée"
        OVERDUE = "OVERDUE", "En retard"

    number = models.CharField(
        "numéro de facture",
        max_length=40,
        unique=True,
        editable=False,
    )
    patient = models.ForeignKey(
        Patient,
        on_delete=models.PROTECT,
        related_name="invoices",
        verbose_name="patient",
    )
    consultation_date = models.DateField(
        "date de consultation",
        default=timezone.localdate,
    )
    consultation_fee = models.DecimalField(
        "prix de consultation (TND)",
        max_digits=10,
        decimal_places=3,
    )
    due_date = models.DateField(
        "date limite de paiement",
        blank=True,
        null=True,
    )
    created_at = models.DateTimeField("créée le", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_invoices",
        verbose_name="créée par",
    )
    notes = models.TextField("notes administratives", blank=True)

    class Meta:
        ordering = ["-consultation_date", "-created_at"]
        verbose_name = "facture de consultation"
        verbose_name_plural = "factures de consultation"
        constraints = [
            models.CheckConstraint(
                condition=Q(consultation_fee__gt=0),
                name="billing_invoice_fee_positive",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = f"FAC-{uuid.uuid4().hex.upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.number

    @property
    def amount_paid(self):
        annotated_total = getattr(self, "paid_total", None)
        if annotated_total is not None:
            return annotated_total
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0.000")

    @property
    def remaining_amount(self):
        return self.consultation_fee - self.amount_paid

    @property
    def financial_status(self):
        if self.remaining_amount <= 0:
            return self.FinancialStatus.PAID
        if self.due_date and self.due_date < timezone.localdate():
            return self.FinancialStatus.OVERDUE
        if self.amount_paid > 0:
            return self.FinancialStatus.PARTIAL
        if self.due_date and self.due_date > timezone.localdate():
            return self.FinancialStatus.DEFERRED
        return self.FinancialStatus.UNPAID

    @property
    def financial_status_display(self):
        return self.FinancialStatus(self.financial_status).label


class Payment(models.Model):
    class Method(models.TextChoices):
        CASH = "CASH", "Espèces"
        CARD = "CARD", "Carte bancaire"
        TRANSFER = "TRANSFER", "Virement"
        CHEQUE = "CHEQUE", "Chèque"
        OTHER = "OTHER", "Autre"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
        verbose_name="facture",
    )
    amount = models.DecimalField(
        "montant payé (TND)",
        max_digits=10,
        decimal_places=3,
    )
    method = models.CharField(
        "moyen de paiement",
        max_length=12,
        choices=Method.choices,
    )
    paid_at = models.DateTimeField(
        "date et heure du paiement",
        default=timezone.now,
    )
    reference = models.CharField("référence", max_length=100, blank=True)
    notes = models.CharField("note", max_length=250, blank=True)
    created_at = models.DateTimeField("enregistré le", auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_payments",
        verbose_name="enregistré par",
    )

    class Meta:
        ordering = ["-paid_at", "-pk"]
        verbose_name = "paiement"
        verbose_name_plural = "paiements"
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0),
                name="billing_payment_amount_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.paid_at and self.paid_at > timezone.now():
            raise ValidationError(
                {"paid_at": "La date d’un paiement ne peut pas être dans le futur."}
            )

    def __str__(self):
        return f"{self.amount} TND — {self.invoice.number}"
