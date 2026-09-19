"""Seed the ritual (Puja) entry point.

``AGENTS.md`` §1 requires discovery through six entry points — Product ·
Category · Festival · **Puja** · Samagri · Ready-made Kit. The Puja one had no
model, endpoint or page at all; this command fills it.

**Every item list is derived from data the project already asserts**, so no new
religious claim is invented:

* the seven kit-backed rituals take their samagri straight from the kit that
  already ships for them, keeping the same ``is_required`` split;
* ``Daily Puja`` takes the products the recommender's own ``STAPLE_CATEGORIES``
  already designates as "everyday puja essential".

This is a **command, not a data migration**, and that is deliberate. Products,
categories and kits are created by ``seed_data``, not by any migration, so a
migration seeding puja items would find an empty catalogue on a fresh database
and quietly produce rituals with no samagri. It would look like it worked.

Idempotent and non-destructive: re-running updates descriptions and tops up
missing items, and never deletes a row.

Usage:
    ./venv/Scripts/python.exe manage.py seed_pujas
    ./venv/Scripts/python.exe manage.py seed_pujas --check
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from festivals.models import FestivalKit, Puja, PujaItem
from festivals.recommender import STAPLE_CATEGORIES
from products.models import Product

DAILY_PUJA_DESCRIPTION = (
    'The everyday household ritual. These are the items the store treats as '
    'daily essentials — the ones you replace most often.'
)

FALLBACK_DESCRIPTION = 'Samagri for this ritual. The item list is being prepared.'

# (name, slug, occasion_type, source)
#   source = 'kit:<festival_type>' → take the samagri from that kit
#   source = 'staples'             → take the recommender's everyday essentials
PUJAS = [
    ('Daily Puja', 'daily-puja', 'other', 'staples'),
    ('Dashain Tika', 'dashain-tika', 'dashain', 'kit:dashain'),
    ('Tihar Laxmi Puja', 'tihar-laxmi-puja', 'tihar', 'kit:tihar'),
    ('Maha Shivaratri Puja', 'maha-shivaratri-puja', 'shivaratri', 'kit:shivaratri'),
    ('Bratabandha', 'bratabandha', 'bratabandha', 'kit:bratabandha'),
    ('Pasni (Rice Feeding)', 'pasni-rice-feeding', 'pasni', 'kit:pasni'),
    ('Griha Pravesh', 'griha-pravesh', 'griha_pravesh', 'kit:griha_pravesh'),
    ('Shraddha', 'shraddha', 'shraddha', 'kit:shraddha'),
]


class Command(BaseCommand):
    help = 'Seed the ritual (Puja) entry point from existing kit and product data.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check', action='store_true',
            help='Report what would change without writing anything.',
        )

    def handle(self, *args, **options):
        dry_run = options['check']
        # Per-ritual chatter is opt-in; the summary is the normal output. Keeps
        # `manage.py test` readable, since the test suite calls this command.
        verbose = options['verbosity'] >= 2
        created_count = 0
        updated_count = 0
        item_count = 0

        for name, slug, occasion_type, source in PUJAS:
            kit = None
            if source.startswith('kit:'):
                kit = FestivalKit.objects.filter(
                    festival_type=source.split(':', 1)[1]
                ).first()

            if kit is not None:
                description = kit.description
            elif source == 'staples':
                description = DAILY_PUJA_DESCRIPTION
            else:
                # The kit this ritual belongs to has not been seeded yet. Say so
                # rather than inventing a description for it.
                description = FALLBACK_DESCRIPTION

            existing = Puja.objects.filter(slug=slug).first()
            if existing is None:
                created_count += 1
                if verbose:
                    self.stdout.write(f'  + create {name}  (source={source})')
                if not dry_run:
                    puja = Puja.objects.create(
                        name=name, slug=slug,
                        occasion_type=occasion_type, description=description,
                    )
                else:
                    puja = None
            else:
                puja = existing
                if (existing.name, existing.occasion_type, existing.description) != (
                    name, occasion_type, description
                ):
                    updated_count += 1
                    if verbose:
                        self.stdout.write(f'  ~ update {name}')
                    if not dry_run:
                        existing.name = name
                        existing.occasion_type = occasion_type
                        existing.description = description
                        existing.save(update_fields=['name', 'occasion_type', 'description'])
                elif verbose:
                    self.stdout.write(f'  = {name} already current')

            if dry_run or puja is None:
                continue

            item_count += self._seed_items(puja, kit, source)

        if options['verbosity'] < 1:
            return

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN — nothing written.'))
            self.stdout.write(
                f'Would create {created_count} and update {updated_count} ritual(s).'
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Pujas: {created_count} created, {updated_count} updated, '
                    f'{item_count} item(s) added. '
                    f'{Puja.objects.count()} puja(s) total, '
                    f'{PujaItem.objects.count()} item(s) total.'
                )
            )

    def _seed_items(self, puja, kit, source):
        """Add any missing items. Existing rows are left exactly as they are."""
        added = 0

        if kit is not None:
            # Link the sellable bundle to the ritual it serves.
            if kit.puja_id != puja.pk:
                kit.puja = puja
                kit.save(update_fields=['puja'])
            source_items = [
                (item.product, item.quantity, item.is_required)
                for item in kit.items.select_related('product')
            ]
        elif source == 'staples':
            source_items = [
                (product, 1, True)
                for product in Product.objects.filter(
                    is_active=True, category__name__in=STAPLE_CATEGORIES,
                ).order_by('-popularity_score', 'id')
            ]
        else:
            source_items = []

        with transaction.atomic():
            for product, quantity, is_required in source_items:
                _, was_created = PujaItem.objects.get_or_create(
                    puja=puja, product=product,
                    defaults={'quantity': quantity, 'is_required': is_required},
                )
                if was_created:
                    added += 1

        return added
