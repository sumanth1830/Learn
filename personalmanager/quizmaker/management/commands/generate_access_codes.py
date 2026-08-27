import secrets

from django.core.management.base import BaseCommand
from quizmaker.models import PilotAccessCode


class Command(BaseCommand):
    help = "Generates a batch of pilot access codes"

    def add_arguments(self, parser):
        parser.add_argument("count", type=int, help="How many codes to generate")
        parser.add_argument("--note", type=str, default="", help="Optional label for this batch")

    def handle(self, *args, **options):
        count = options["count"]
        note = options["note"]

        codes = []
        for _ in range(count):
            code = secrets.token_urlsafe(6)
            PilotAccessCode.objects.create(code=code, note=note)
            codes.append(code)

        self.stdout.write(self.style.SUCCESS(f"Generated {count} code(s):"))
        for code in codes:
            self.stdout.write(f"  {code}")