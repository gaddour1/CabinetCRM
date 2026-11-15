from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.operations.models import DeleteModel
from django.db.migrations.operations.fields import RemoveField
from django.db.migrations.operations.special import (
    RunPython,
    RunSQL,
    SeparateDatabaseAndState,
)


SAFE_DATA_MIGRATIONS = {
    ("consultations", "0003_consultation_biological_exams_and_more"),
    ("consultations", "0006_optional_consultation_fee"),
    ("contenttypes", "0002_remove_content_type_name"),
    ("auth", "0011_update_proxy_permissions"),
}
SAFE_FIELD_REMOVALS = {
    (
        "consultations",
        "0006_optional_consultation_fee",
        "consultation",
        "invoice",
    ),
    (
        "contenttypes",
        "0002_remove_content_type_name",
        "contenttype",
        "name",
    ),
}


def _database_operations(operation):
    if isinstance(operation, SeparateDatabaseAndState):
        for child in operation.database_operations:
            yield from _database_operations(child)
    else:
        yield operation


class Command(BaseCommand):
    help = "Refuse to run pending migrations with unreviewed destructive operations."

    def handle(self, *args, **options):
        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
        errors = []

        for migration, _backwards in plan:
            migration_key = (migration.app_label, migration.name)
            for operation in migration.operations:
                for database_operation in _database_operations(operation):
                    if isinstance(database_operation, DeleteModel):
                        errors.append(
                            f"{migration.app_label}.{migration.name} "
                            f"supprime le modèle {database_operation.name}."
                        )
                    elif isinstance(database_operation, RemoveField):
                        field_key = (
                            migration.app_label,
                            migration.name,
                            database_operation.model_name,
                            database_operation.name,
                        )
                        if field_key not in SAFE_FIELD_REMOVALS:
                            errors.append(
                                f"{migration.app_label}.{migration.name} "
                                f"supprime le champ "
                                f"{database_operation.model_name}."
                                f"{database_operation.name}."
                            )
                    elif isinstance(database_operation, (RunPython, RunSQL)):
                        if migration_key not in SAFE_DATA_MIGRATIONS:
                            errors.append(
                                f"{migration.app_label}.{migration.name} "
                                "contient une opération de données/SQL non validée."
                            )

        if errors:
            raise CommandError(
                "Migrations non exécutées : opérations destructrices non validées.\n"
                + "\n".join(f"- {error}" for error in errors)
                + "\nContactez le support Cabinet avant de poursuivre."
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"{len(plan)} migration(s) en attente : aucune opération "
                "destructrice non validée."
            )
        )
