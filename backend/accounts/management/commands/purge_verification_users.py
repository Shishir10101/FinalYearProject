"""Delete scratch user accounts created by the verification scripts.

The Day 4 verifier has to register a throwaway account to prove the password
reset flow works end to end — there is no way to test "the new password really
authenticates" without an account whose password it is allowed to change.

That account must not survive the run. Rather than leaving a stray login in the
demo (which would be a genuine security smell on a handover), this command
removes accounts whose username carries a verifier prefix. The prefix match is
deliberately narrow: it can never match `admin`, `testuser` or `vendor1`.

Usage:
    ./venv/Scripts/python.exe manage.py purge_verification_users
    ./venv/Scripts/python.exe manage.py purge_verification_users --dry-run
"""

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

# Prefix, not "contains": a prefix cannot accidentally match a real account.
# Deliberately broad enough to cover every verifier (verifyday4probe,
# verifyday7probe, …) so a new one does not silently leave an account behind.
USERNAME_PREFIXES = [
    'verifyday',
    'verify_day',
]

# Belt and braces — these must never be removed, whatever the prefixes say.
PROTECTED = ['admin', 'testuser', 'vendor1']


class Command(BaseCommand):
    help = 'Delete verification-script user accounts (matched by username prefix).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be deleted without deleting anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        matched = User.objects.none()
        for prefix in USERNAME_PREFIXES:
            matched = matched | User.objects.filter(username__istartswith=prefix)
        matched = matched.exclude(username__in=PROTECTED)

        # Resolve to a plain id list before deleting. The queryset carries a
        # DISTINCT from combining the prefixes with `|`, and Django refuses
        # `delete()` on a distinct queryset ("Cannot call delete() after
        # .distinct()"). Collecting ids first also freezes the target set, so the
        # command deletes exactly what it printed.
        ids = list(matched.values_list('id', flat=True).distinct())
        usernames = list(
            User.objects.filter(id__in=ids).order_by('id').values_list('username', flat=True)
        )

        if not ids:
            self.stdout.write('No verification users found.')
        else:
            self.stdout.write(f'Matched {len(ids)} verification user(s):')
            for user in User.objects.filter(id__in=ids).order_by('id'):
                self.stdout.write(
                    f'  id={user.id} username={user.username!r} email={user.email!r}'
                )

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing deleted.'))
            self.stdout.write(f'Would delete {len(ids)} user(s).')
            return

        with transaction.atomic():
            deleted, _ = User.objects.filter(id__in=ids).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {len(usernames)} verification user(s) '
                f'({deleted} rows including profiles). '
                f'{User.objects.count()} user(s) remain: '
                f'{", ".join(User.objects.order_by("id").values_list("username", flat=True))}'
            )
        )
