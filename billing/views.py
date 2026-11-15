from decimal import Decimal
from datetime import datetime

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import DecimalField, Exists, OuterRef, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string

from accounts.decorators import doctor_required

from .forms import InvoiceForm, PaymentForm
from .models import Invoice, Payment
from .services import record_payment


INVOICE_SORTS = {
    "date": ("consultation_date", "created_at"),
    "patient": ("patient__last_name", "patient__first_name"),
    "number": ("number",),
    "amount": ("consultation_fee",),
    "paid": ("paid_total",),
    "due_date": ("due_date",),
}


def _search_date(term):
    for date_format in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(term, date_format).date()
        except ValueError:
            continue
    return None


@doctor_required
def invoice_list(request):
    invoices = Invoice.objects.select_related("patient").annotate(
        paid_total=Coalesce(
            Sum("payments__amount"),
            Value(
                Decimal("0.000"),
                output_field=DecimalField(max_digits=10, decimal_places=3),
            ),
        )
    )
    query = request.GET.get("q", "").strip()
    if query:
        for index, term in enumerate(query.split()):
            payment_reference = f"payment_reference_match_{index}"
            matching = (
                Q(number__icontains=term)
                | Q(patient__first_name__icontains=term)
                | Q(patient__last_name__icontains=term)
                | Q(patient__cin__icontains=term)
                | Q(patient__phone__icontains=term)
                | Q(patient__record_number__icontains=term)
            )
            date_value = _search_date(term)
            if date_value:
                matching |= (
                    Q(consultation_date=date_value)
                    | Q(due_date=date_value)
                    | Q(patient__date_of_birth=date_value)
                    | Q(created_at__date=date_value)
                )
            invoices = invoices.annotate(
                **{
                    payment_reference: Exists(
                        Payment.objects.filter(
                            invoice_id=OuterRef("pk"),
                            reference__icontains=term,
                        )
                    )
                }
            ).filter(matching | Q(**{payment_reference: True}))

    sort = request.GET.get("sort", "date")
    if sort not in INVOICE_SORTS:
        sort = "date"
    direction = request.GET.get("direction", "desc")
    if direction not in {"asc", "desc"}:
        direction = "desc"
    invoices = invoices.order_by(
        *(f"-{field}" if direction == "desc" else field for field in INVOICE_SORTS[sort]),
        "-pk",
    )
    context = {
        "invoices": invoices,
        "query": query,
        "sort": sort,
        "direction": direction,
        "sort_options": (
            ("date", "Date de consultation"),
            ("patient", "Patient (A–Z)"),
            ("number", "Numéro de facture"),
            ("amount", "Montant facturé"),
            ("paid", "Montant payé"),
            ("due_date", "Date limite"),
        ),
    }
    if request.GET.get("partial") == "1":
        rows = render_to_string(
            "billing/partials/invoice_rows.html",
            context,
            request=request,
        )
        return JsonResponse({"rows": rows, "count": invoices.count()})
    return render(
        request,
        "billing/invoice_list.html",
        context,
    )


@doctor_required
def invoice_create(request):
    form = InvoiceForm(
        request.POST or None,
        patient_id=request.GET.get("patient"),
    )
    if request.method == "POST" and form.is_valid():
        invoice = form.save(commit=False)
        invoice.created_by = request.user
        invoice.save()
        messages.success(request, f"La facture {invoice.number} a été créée.")
        return redirect("billing:invoice_detail", invoice_id=invoice.pk)
    return render(
        request,
        "billing/invoice_form.html",
        {"form": form},
    )


@doctor_required
def invoice_detail(request, invoice_id):
    invoice = get_object_or_404(
        Invoice.objects.select_related("patient", "created_by").annotate(
            paid_total=Coalesce(
                Sum("payments__amount"),
                Value(
                    Decimal("0.000"),
                    output_field=DecimalField(max_digits=10, decimal_places=3),
                ),
            )
        ),
        pk=invoice_id,
    )
    payment_form = PaymentForm()
    if request.method == "POST":
        payment_form = PaymentForm(request.POST)
        if payment_form.is_valid():
            try:
                record_payment(
                    invoice_id=invoice.pk,
                    created_by=request.user,
                    **payment_form.cleaned_data,
                )
            except ValidationError as error:
                payment_form.add_error(None, error)
            else:
                messages.success(request, "Le paiement a été enregistré.")
                return redirect("billing:invoice_detail", invoice_id=invoice.pk)
    return render(
        request,
        "billing/invoice_detail.html",
        {
            "invoice": invoice,
            "payment_form": payment_form,
            "payments": invoice.payments.select_related("created_by").all(),
        },
    )
