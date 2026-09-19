"""Backfill ``OrderStatusEvent`` rows for orders that predate status tracking.

Everything before this migration has **no** recorded history — the status was a
single mutable column, so the only thing we can honestly say about an old order
is the state it is in *now*.

Two wrong ways to handle that, both of which this migration deliberately avoids:

1. **Invent a ladder.** Creating a fake ``pending → confirmed → … → shipped``
   sequence with plausible-looking timestamps would make the demo screens look
   complete while putting fabricated dates in front of the customer. The whole
   project takes a position against presenting invented data as real, and a
   fabricated delivery date is worse than a missing one.
2. **Write nothing.** Then the timeline falls back to ``Order.created_at`` and
   silently implies an order placed three weeks ago was shipped the same minute.

So: exactly one event per pre-existing order, stamped with that order's real
``created_at``, carrying the status it currently holds and a note saying where
the row came from. Steps with no event render as "not recorded" in the UI rather
than borrowing a timestamp they never had.

``created_at`` is set explicitly. ``auto_now_add`` would have ignored it — and
note that historical models inside a migration have no overridden ``save()``, the
same trap that once shipped a blank vendor slug.
"""

from django.db import migrations
from django.utils import timezone

BACKFILL_NOTE = 'Backfilled from the order\'s recorded status; earlier timestamps were not tracked.'


def backfill_events(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    OrderStatusEvent = apps.get_model('orders', 'OrderStatusEvent')

    for order in Order.objects.all().iterator():
        # Idempotent: re-running must not duplicate history.
        if OrderStatusEvent.objects.filter(order=order).exists():
            continue
        OrderStatusEvent.objects.create(
            order=order,
            from_status='',
            to_status=order.status,
            note=BACKFILL_NOTE,
            created_at=order.created_at or timezone.now(),
        )


def unbackfill_events(apps, schema_editor):
    """Reverse by removing only the rows this migration wrote.

    Matching on the note means any event created by real activity after the
    migration ran is left alone, so the reverse is safe even on a database that
    has been used since.
    """
    OrderStatusEvent = apps.get_model('orders', 'OrderStatusEvent')
    OrderStatusEvent.objects.filter(note=BACKFILL_NOTE, from_status='').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_orderstatusevent'),
    ]

    operations = [
        migrations.RunPython(backfill_events, unbackfill_events),
    ]
