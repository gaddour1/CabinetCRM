from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import Invoice, Payment


@transaction.atomic
def record_payment(*, invoice_id, amount, method, paid_at, created_by, reference="", notes=""):
    invoice = Invoice.objects.select_for_update().get(pk=invoice_id)
    total_paid = invoice.payments.aggregate(total=Sum("amount"))["total"] or Decimal(
        "0.000"
    )
    remaining = invoice.consultation_fee - total_paid

    if amount > remaining:
        raise ValidationError(
            f"Le paiement dépasse le solde restant de {remaining:.3f} TND."
        )

    payment = Payment(
        invoice=invoice,
        amount=amount,
        method=method,
        paid_at=paid_at,
        created_by=created_by,
        reference=reference,
        notes=notes,
    )
    payment.full_clean()
    payment.save()
    return payment
