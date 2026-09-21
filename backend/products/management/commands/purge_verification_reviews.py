"""Delete reviews created by the verification scripts.

A review left behind is not cosmetic: it changes the rating and the review count of a
**seeded product**, so the demo's own data would quietly disagree with what the seeder
produced. `verify_day11.py` deletes its own reviews, but an interrupted run cannot, and
that is exactly when this is needed.

Matching is on a marker in the review body, so a review a real customer wrote is never
swept up. Reviews written by the browser harness are matched too — it uses the same
marker convention.

    python manage.py purge_verification_reviews --dry-run
    python manage.py purge_verification_reviews
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from products.models import Review

# Each verifier writes a marker into Review.body. Matching on the marker is safer than
# "everything with no order behind it", because a legitimate review of something bought
# elsewhere must never be removed.
MARKERS = [
    'verify_day11.py',
    'browser_check.mjs',
]


class Command(BaseCommand):
    help = 'Delete reviews created by the verification scripts (marked in the body).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be deleted without deleting anything.',
        )

    def handle(self, *args, **options):
        query = Q()
        for marker in MARKERS:
            query |= Q(body__icontains=marker) | Q(title__icontains=marker)

        matches = Review.objects.filter(query).select_related('product', 'user')

        if not matches.exists():
            self.stdout.write('No verification reviews found.')
            return

        self.stdout.write(f'Matched {matches.count()} verification review(s):')
        for review in matches:
            self.stdout.write(
                f'  id={review.id} product={review.product.name[:30]!r} '
                f'user={review.user.username!r} rating={review.rating}'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'DRY RUN — nothing deleted. Would delete {matches.count()} review(s).'
            ))
            return

        deleted, _ = matches.delete()
        remaining = Review.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'Deleted {deleted} review row(s). {remaining} review(s) remain.'
        ))
