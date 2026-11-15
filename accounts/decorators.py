from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def doctor_required(view):
    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        if not request.user.can_access_medical_records:
            raise PermissionDenied("Accès réservé au personnel médical autorisé.")
        return view(request, *args, **kwargs)

    return wrapped
