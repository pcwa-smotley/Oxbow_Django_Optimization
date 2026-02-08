from django.core.management.base import BaseCommand, CommandError

from celery.exceptions import TimeoutError as CeleryTimeoutError
from kombu.exceptions import OperationalError

from django_backend.celery import app


class Command(BaseCommand):
    help = "Ping the Celery worker and exit with a non-zero status if it is unreachable."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=float,
            default=2.0,
            help="Seconds to wait for the Celery worker to respond to the ping.",
        )
        parser.add_argument(
            "--silent",
            action="store_true",
            help="Suppress success output (useful for editor preLaunch tasks).",
        )

    def handle(self, *args, **options):
        timeout = options["timeout"]
        inspector = app.control.inspect(timeout=timeout)

        try:
            responses = inspector.ping() or {}
        except (CeleryTimeoutError, OperationalError) as exc:
            raise CommandError(
                "Unable to reach a Celery worker. Start one with `celery -A django_backend worker -l info`.") from exc

        if not responses:
            raise CommandError(
                "No running Celery workers detected. Start one with `celery -A django_backend worker -l info`."
            )

        if not options["silent"]:
            workers = ", ".join(sorted(responses.keys()))
            self.stdout.write(self.style.SUCCESS(f"Celery worker(s) responding: {workers}"))