from django.db import migrations, models
import django.db.models.deletion


def copy_consultation_fees(apps, schema_editor):
    Consultation = apps.get_model("consultations", "Consultation")
    for consultation in Consultation.objects.select_related("invoice").iterator():
        Consultation.objects.filter(pk=consultation.pk).update(
            consultation_fee=consultation.invoice.consultation_fee
        )


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
        ("consultations", "0005_alter_consultation_reason"),
    ]

    operations = [
        migrations.AddField(
            model_name="consultation",
            name="consultation_fee",
            field=models.DecimalField(
                blank=True,
                decimal_places=3,
                max_digits=10,
                null=True,
                verbose_name="prix de la consultation (TND)",
            ),
        ),
        migrations.RunPython(copy_consultation_fees, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="consultation",
            name="invoice",
        ),
        migrations.AlterField(
            model_name="consultation",
            name="patient",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="consultations",
                to="patients.patient",
                verbose_name="patient",
            ),
        ),
    ]
