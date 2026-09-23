"""Delete scratch orders created by the verification scripts.

Verification scripts exercise the real checkout path, which means they create
real rows. Cancelling them leaves the demo order history cluttered and makes
order ids jump (the admin UI shows "21" right after "10"). This command removes
only rows whose ``notes`` carry a verifier marker, so seeded demo orders are
never touched.

**It also returns their stock, and reverses their popularity.** A verifier order reserves
inventory the same way a real one does — `CheckoutView` decrements `product.stock` and
increments `product.popularity_score` — and deleting the row without undoing either leaked
both. Every verification sweep quietly shrank the catalogue's stock (measured before the fix:
**538 units across 23 products**) and inflated its demand signal (**591 popularity points**),
which then produced false low-stock and restock alerts, skewed the default catalogue order,
and biased the recommendation engine's popularity bonus toward whatever the tests bought.

Two different rules, deliberately:

* **stock** is released only for orders that still hold a reservation. A cancelled order
  already gave its units back, so releasing again would inflate inventory by exactly as much
  as the old bug deflated it.
* **popularity** is reversed for *every* order being deleted, cancelled or not, because
  cancellation never reverses it — a real cancelled order still means a customer asked for
  something, but a fixture order means nobody did.

Usage:
    ./venv/Scripts/python.exe manage.py purge_verification_orders
    ./venv/Scripts/python.exe manage.py purge_verification_orders --dry-run
    ./venv/Scripts/python.exe manage.py purge_verification_orders --no-restock
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from orders.models import Cart, Order
from orders.views import release_order_stock, reverse_order_popularity

# Each verifier writes a marker into Order.notes. Matching on the marker is
# safer than matching on "everything that is not seeded", because a real
# customer order placed during a demo must never be swept up.
MARKERS = [
    'verify_day4.py',
    'verify_day3c.py',
    'created by verify_day3b.py',
    'verify_day3.py',
    'verify_day2.py',
    # The storefront browser check places one real order through the checkout form
    # and writes this marker into its notes, so it is swept up with the rest.
    'browser_check.mjs',
    # verify_day11.py buys a product so it can prove the "verified purchase" badge on
    # a review. The order is a fixture, not a demo order.
    'verify_day11.py',
    # verify_day13.py checks out nothing, but the area-breakdown checks read orders, so
    # keep the marker list complete for anything it may add later.
    'verify_day13.py',
    # Day 14's mocked-payment check places an eSewa order to prove the disclosure flag
    # and the honest history note reach the payload. Without this entry the order would
    # survive every sweep — which is precisely the mistake this list exists to prevent,
    # and it was caught by running the purge rather than by assuming it covered the file.
    'verify_day14_disclosure.py',
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
        parser.add_argument(
            '--no-restock', action='store_true',
            help=(
                'Delete the orders without touching the catalogue at all — no stock '
                'returned and no popularity reversed.'
            ),
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        restock = not options['no_restock']

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

        # Two different rules, for two different fields, and the difference is the point:
        #
        #  * **stock** is released only for orders that still hold a reservation. A
        #    cancelled order already gave its units back, so releasing again here would
        #    inflate inventory by exactly as much as the old bug deflated it.
        #  * **popularity** is reversed for *every* order being deleted, cancelled or
        #    not, because cancellation deliberately never reverses it — a real cancelled
        #    order still means a customer asked. A fixture order means nobody did.
        holding = [o for o in scratch if o.status != 'cancelled'] if restock else []
        units = sum(i.quantity for o in holding for i in o.items.all())
        points = sum(i.quantity for o in scratch for i in o.items.all()) if restock else 0

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing deleted.'))
            self.stdout.write(f'Would delete {len(ids)} order(s).')
            if restock:
                self.stdout.write(
                    f'Would return {units} unit(s) to stock '
                    f'from {len(holding)} non-cancelled order(s).'
                )
                self.stdout.write(
                    f'Would reverse up to {points} popularity point(s) across '
                    f'{len(ids)} order(s).'
                )
            if not options['keep_cart']:
                self.stdout.write(f'Would clear {cart_count} cart line(s).')
            return

        with transaction.atomic():
            if restock:
                for order in holding:
                    release_order_stock(order)
                for order in scratch:
                    reverse_order_popularity(order)
            if ids:
                Order.objects.filter(id__in=ids).delete()
            if not options['keep_cart']:
                Cart.objects.all().delete()

        self.stdout.write(
            self.style.SUCCESS(
                f'Deleted {len(ids)} verification order(s); '
                f'cleared {cart_count} cart line(s)'
                + (f'; returned {units} unit(s) to stock; reversed {points} popularity point(s)'
                   if restock else '')
                + f'. {Order.objects.count()} order(s) remain.'
            )
        )

