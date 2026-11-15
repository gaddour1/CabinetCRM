from django.urls import path

from . import views

app_name = "consultations"

urlpatterns = [
    path("", views.consultation_list, name="list"),
    path("nouvelle/", views.consultation_create, name="create"),
    path("suggestions/", views.medical_suggestion_list, name="suggestions"),
    path(
        "suggestions/api/",
        views.medical_suggestions_api,
        name="suggestions_api",
    ),
    path(
        "suggestions/<int:suggestion_id>/utiliser/",
        views.medical_suggestion_use,
        name="suggestions_use",
    ),
    path(
        "suggestions/nouvelle/",
        views.medical_suggestion_create,
        name="suggestion_create",
    ),
    path(
        "suggestions/<int:suggestion_id>/modifier/",
        views.medical_suggestion_update,
        name="suggestion_update",
    ),
    path(
        "suggestions/<int:suggestion_id>/archiver/",
        views.medical_suggestion_toggle_archive,
        name="suggestion_archive",
    ),
    path(
        "<int:consultation_id>/supprimer/",
        views.consultation_delete,
        name="delete",
    ),
    path("<int:consultation_id>/modifier/", views.consultation_update, name="update"),
    path("<int:consultation_id>/", views.consultation_detail, name="detail"),
]
