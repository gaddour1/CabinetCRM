from django.urls import path

from . import views

app_name = "patients"

urlpatterns = [
    path("", views.patient_list, name="list"),
    path("nouveau/", views.patient_create, name="create"),
    path("<int:patient_id>/", views.patient_detail, name="detail"),
    path("<int:patient_id>/modifier/", views.patient_update, name="update"),
    path("<int:patient_id>/archiver/", views.patient_archive, name="archive"),
    path("<int:patient_id>/restaurer/", views.patient_restore, name="restore"),
]
