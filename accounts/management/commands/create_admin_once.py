import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser

MIN_PASSWORD_LENGTH = 8


class Command(BaseCommand):
    help = "Create the initial admin account once; safe to run on every deploy."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--email",
            default=os.getenv("ADMIN_EMAIL", ""),
            help="Admin email. Defaults to the ADMIN_EMAIL environment variable.",
        )
        parser.add_argument(
            "--password",
            default=os.getenv("ADMIN_PASSWORD", ""),
            help="Admin password. Defaults to the ADMIN_PASSWORD environment variable.",
        )
        parser.add_argument(
            "--first-name",
            default=os.getenv("ADMIN_FIRST_NAME", "Admin"),
            help="First name used when the account is created.",
        )
        parser.add_argument(
            "--reset-password",
            action="store_true",
            help="Overwrite the password when the account already exists.",
        )

    def handle(self, *args: object, **options: object) -> None:
        email = str(options["email"] or "").strip().lower()
        password = str(options["password"] or "")
        first_name = str(options["first_name"] or "")
        reset_password = bool(options["reset_password"])

        if not email:
            self.stdout.write(
                "ADMIN_EMAIL is not set; skipping admin provisioning."
            )
            return

        user_model = get_user_model()
        user = user_model.objects.filter(email=email).first()

        if user is None:
            if len(password) < MIN_PASSWORD_LENGTH:
                raise CommandError(
                    "A password of at least "
                    f"{MIN_PASSWORD_LENGTH} characters is required. "
                    "Pass --password or set ADMIN_PASSWORD."
                )
            user = user_model.objects.create_superuser(
                email=email,
                password=password,
                first_name=first_name,
            )
            self.stdout.write(self.style.SUCCESS(f"Created admin {user.email}."))
            return

        changed: list[str] = []
        if not user.is_staff:
            user.is_staff = True
            changed.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            changed.append("is_superuser")
        if not user.is_active:
            user.is_active = True
            changed.append("is_active")
        if reset_password and password:
            user.set_password(password)
            changed.append("password")

        if changed:
            user.save(update_fields=changed)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated admin {user.email}: {', '.join(changed)}."
                )
            )
            return

        self.stdout.write(f"Admin {user.email} already exists; nothing to do.")
