import json
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import User


class Command(BaseCommand):
    help = "Create the first doctor account during local clinic setup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report whether a doctor account must be created.",
        )

    def handle(self, *args, **options):
        if options["check"]:
            required = not User.objects.exists()
            self.stdout.write(f"CABINET_DOCTOR_REQUIRED={int(required)}")
            return

        try:
            credentials = json.load(sys.stdin)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise CommandError("Invalid account setup data.") from error

        if not isinstance(credentials, dict):
            raise CommandError("Invalid account setup data.")
        username = credentials.get("username", "")
        password = credentials.get("password", "")
        first_name = credentials.get("first_name", "")
        last_name = credentials.get("last_name", "")
        if (
            not isinstance(username, str)
            or not isinstance(password, str)
            or not isinstance(first_name, str)
            or not isinstance(last_name, str)
            or not username
            or not password
        ):
            raise CommandError("A username and password are required.")
        username = username.strip()
        first_name = first_name.strip()
        last_name = last_name.strip()
        if not username:
            raise CommandError("A username and password are required.")

        try:
            User._meta.get_field(User.USERNAME_FIELD).clean(username, None)
            user = User(username=username, first_name=first_name, last_name=last_name)
            User._meta.get_field("first_name").clean(first_name, user)
            User._meta.get_field("last_name").clean(last_name, user)
            validate_password(password, user=user)
        except ValidationError as error:
            raise CommandError("; ".join(error.messages)) from error

        with transaction.atomic():
            if User.objects.exists():
                raise CommandError(
                    "A user already exists; the initial account was not changed."
                )
            User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role=User.Role.DOCTOR,
            )

        self.stdout.write("The initial doctor account was created.")
