from django.shortcuts import render
from django.utils import timezone

from accounts.decorators import doctor_required
from accounts.models import User
from patients.models import Patient


@doctor_required
def dashboard(request):
    today = timezone.localdate()
    context = {
        "patient_count": Patient.objects.filter(archived_at__isnull=True).count(),
        "new_today_count": Patient.objects.filter(created_at__date=today).count(),
        "doctor_count": User.objects.filter(
            role=User.Role.DOCTOR, is_active=True
        ).count(),
        "recent_patients": Patient.objects.filter(
            archived_at__isnull=True
        ).order_by("-created_at")[:5],
    }
    return render(request, "core/dashboard.html", context)
