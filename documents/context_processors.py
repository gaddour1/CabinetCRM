from django.conf import settings
from django.contrib.staticfiles import finders


def cabinet_info(_request):
    info = settings.CABINET_INFO.copy()
    info["logo_available"] = finders.find(info["logo"]) is not None
    return {"cabinet_info": info}
