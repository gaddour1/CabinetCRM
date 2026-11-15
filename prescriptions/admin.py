from django.contrib import admin

from .models import (
    MedicationLibraryEntry,
    Prescription,
    PrescriptionRevision,
    PrescribedMedication,
)


class PrescribedMedicationInline(admin.TabularInline):
    model = PrescribedMedication
    extra = 0


@admin.register(Prescription)
class PrescriptionAdmin(admin.ModelAdmin):
    list_display = (
        "consultation",
        "prescriber",
        "status",
        "created_at",
        "validated_at",
    )
    list_filter = ("status",)
    search_fields = (
        "consultation__reference",
        "consultation__patient__first_name",
        "consultation__patient__last_name",
        "prescriber__username",
    )
    inlines = [PrescribedMedicationInline]
    readonly_fields = (
        "status",
        "created_at",
        "updated_at",
        "validated_at",
        "validated_by",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MedicationLibraryEntry)
class MedicationLibraryEntryAdmin(admin.ModelAdmin):
    list_display = ("name", "dosage", "doctor")
    search_fields = ("name", "doctor__username")
    list_filter = ("pharmaceutical_form",)


@admin.register(PrescriptionRevision)
class PrescriptionRevisionAdmin(admin.ModelAdmin):
    list_display = ("prescription", "version_number", "corrected_by", "created_at")
    readonly_fields = (
        "prescription",
        "version_number",
        "snapshot",
        "reason",
        "corrected_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
