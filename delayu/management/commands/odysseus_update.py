"""CLI: managed Odysseus vendor updates."""
from django.core.management.base import BaseCommand, CommandError

from delayu.models import Subsystem
from delayu.services.odysseus_update import apply_update, check_update, rollback_update


class Command(BaseCommand):
    help = "Check / apply / rollback Odysseus vendor pin"

    def add_arguments(self, parser):
        parser.add_argument("--subsystem", default="invest-kk")
        g = parser.add_mutually_exclusive_group(required=True)
        g.add_argument("--check", action="store_true")
        g.add_argument("--apply", metavar="REF")
        g.add_argument("--rollback", action="store_true")

    def handle(self, *args, **options):
        sub = Subsystem.objects.filter(code=options["subsystem"]).first()
        if not sub:
            raise CommandError(f"subsystem not found: {options['subsystem']}")
        try:
            if options["check"]:
                result = check_update(sub)
            elif options["apply"]:
                result = apply_update(sub, options["apply"])
            else:
                result = rollback_update(sub)
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"pinned={result.pinned_ref} head={result.head_ref} "
            f"exists={result.vendor_exists} msg={result.message}"
        )
