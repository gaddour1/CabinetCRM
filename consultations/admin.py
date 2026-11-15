from django.contrib import admin

from .models import MedicalSuggestion


@admin.register(MedicalSuggestion)
class MedicalSuggestionAdmin(admin.ModelAdmin):
    list_display = ("text", "category", "doctor", "is_active", "usage_count")
    list_filter = ("category", "is_active")
    search_fields = ("text", "normalized_text", "doctor__username")
