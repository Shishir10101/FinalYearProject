"""Generate the labelled synthetic sales history used by demand forecasting.

**The data this command writes is fabricated.** It is not real customer demand.
Every row is written to ``analytics.SyntheticSalesRecord`` with
``is_synthetic=True``, and every API response derived from it is flagged
``"data_source": "synthetic"``.

Why it exists: the real database has 8 orders / 20 order items and 5 distinct
products ever sold. That cannot train a demand model. Rather than ship a fake
model or no model at all, we ship a *real* pipeline over an openly *synthetic*
dataset, and the admin UI states that plainly.

The generator is deterministic (fixed seed), so regenerating produces an
identical dataset and the evaluation numbers in ``docs/AI-PREDICTION.md`` stay
reproducible.

Usage::

    python manage.py generate_synthetic_sales
    python manage.py generate_synthetic_sales --purge   # delete and rebuild
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from analytics.forecasting import (
    SYNTHETIC_DAYS,
    SYNTHETIC_SEED,
    SYNTHETIC_START,
    build_synthetic_history,
)
from analytics.models import SyntheticSalesRecord
from products.models import Category, Product


class Command(BaseCommand):
    help = 'Generate the labelled SYNTHETIC sales history for demand forecasting'

    def add_arguments(self, parser):
        parser.add_argument(
            '--purge', action='store_true',
            help='Delete existing synthetic rows first',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        products = list(Product.objects.filter(is_active=True).order_by('id'))
        if not products:
            self.stdout.write(self.style.ERROR('No active products found — aborting.'))
            return

        categories_by_id = dict(Category.objects.values_list('id', 'name'))

        if options['purge']:
            deleted, _ = SyntheticSalesRecord.objects.all().delete()
            self.stdout.write(f'Purged {deleted} existing synthetic rows.')

        series = build_synthetic_history(products, categories_by_id)

        rows = []
        for entry in series:
            for day, units in entry.daily.items():
                context = entry.festival_context.get(day) or ''
                rows.append(SyntheticSalesRecord(
                    product_id=entry.product_id,
                    date=day,
                    units_sold=units,
                    is_synthetic=True,
                    festival_context=context,
                ))

        SyntheticSalesRecord.objects.bulk_create(
            rows, batch_size=1000, ignore_conflicts=True,
        )

        total = SyntheticSalesRecord.objects.count()
        festivals_tagged = SyntheticSalesRecord.objects.exclude(
            festival_context=''
        ).count()

        self.stdout.write(self.style.WARNING(
            'NOTE: the generated data is SYNTHETIC and must never be presented '
            'as real demand.'
        ))
        self.stdout.write(self.style.SUCCESS(
            f'Synthetic history ready: {total} rows across {len(series)} products, '
            f'{SYNTHETIC_DAYS} days from {SYNTHETIC_START.isoformat()} '
            f'(seed {SYNTHETIC_SEED}). {festivals_tagged} rows tagged with a festival.'
        ))
