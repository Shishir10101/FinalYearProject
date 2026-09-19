"""Delete scratch orders created by the verification scripts.

Verification scripts exercise the real checkout path, which means they create
real rows. Cancelling them leaves the demo order history cluttered and makes
order ids jump (the admin UI shows "21" right after "10"). This command removes
only rows whose ``notes`` carry a verifier marker, so seeded demo orders are
never touched.

Usage:
    ./venv/Scripts/python.exe manage.py purge_verification_orders
    ./venv/Scripts/python.exe manage.py purge_verification_orders --dry-run
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from orders.models import Cart, Order

# Each verifier writes a marker into Order.notes. Matching on the marker is
# safer than matching on "everything that is not seeded", because a real
# customer order placed during a demo must never be swept up.
MARKERS = [
    'verify_day4.py',
    'verify_day3c.py',
    'created by verify_day3b.py',
    'verify_day3.py',
    'verify_day2.py',
]

# verify_day3c.py also checks out into a scratch delivery area. That path has no
# notes marker, so it is matched on the address the script writes instead.
EXTRA_ADDRESS_MARKERS = [
    'E2E Area Override Address',
    'E2E Status Ladder Address',
    'E2E Status History Address',
    'E2E Verification Address',
]


class Command(BaseCommand):
    help = 'Delete orders created by the verification scripts (marked in notes).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='List what would be deleted without deleting anything.',
        )
        parser.add_argument(
            '--keep-cart', action='store_true',
            help='Do not clear leftover cart lines.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        query = Q()
        for marker in MARKERS:
            query |= Q(notes__icontains=marker)
        for marker in EXTRA_ADDRESS_MARKERS:
            query |= Q(shipping_address__icontains=marker)

        scratch = Order.objects.filter(query).distinct()

        if not scratch.exists():
            self.stdout.write('No verification orders found.')
        else:
            self.stdout.write(f'Matched {scratch.count()} verification order(s):')
            for order in scratch.order_by('id'):
                self.stdout.write(
                    f'  id={order.id} status={order.status} '
                    f'address={order.shipping_address[:34]!r} '
                    f'notes={order.notes[:40]!r}'
                )

        ids = list(scratch.values_list('id', flat=True))
        cart_count = Cart.objects.count()

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing deleted.'))
            self.stdout.write(f'Would delete {len(ids)} order(s).')
            if not options['keep_cart']:
                self.stdout.write(f'Would clear {cart_count} cart line(s).')
            return

        with transaction.atomic():
            if ids:
                Order.objects.filter(id__in=ids).delete()
            if not options['keep_cart']:
                Cart.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {len(ids)} verification order(s); '
                f'cleared {cart_count} cart line(s). '
                f'{Order.objects.count()} order(s) remain.'
            )
        )

