"""Refresh the upcoming-festival calendar relative to *today*.

Why this exists
---------------
``core.management.commands.seed_data`` creates the festival rows with
``date.today() + timedelta(days=N)``. That is correct at seeding time, but the
database was seeded months ago, so every row is now in the past:

    Maha Shivaratri 2026   2026-04-21   (150 days ago)
    Nag Panchami 2026      2026-05-06   (135 days ago)
    Teej 2026              2026-05-21   (120 days ago)
    Dashain 2026           2026-06-05   (105 days ago)
    Tihar 2026             2026-06-20    (90 days ago)

Consequences before this command existed:

* ``GET /api/festivals/upcoming/`` returned ``[]``, so the home page showed
  "No upcoming festivals scheduled".
* The recommender's entire festival signal was dead, leaving only popularity —
  i.e. the domain differentiator silently degraded into a generic best-seller
  list.

This command is **idempotent and non-destructive**: it updates the ``date`` (and
``is_active``) of existing rows matched by name and only creates rows that are
missing. It never deletes festivals, so any festival kits, orders, or KitItems
that reference a festival type are unaffected.

Festival dates follow the Bikram Sambat lunar calendar, so real-world dates
drift year to year. These are **approximate Nepali festival dates for the next
~12 months**, anchored to today, which is what the demo needs. They are calendar
estimates, not an authoritative panchang.

Usage::

    python manage.py refresh_festivals          # apply
    python manage.py refresh_festivals --check  # report without writing
"""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from festivals.models import UpcomingFestival

# (name, festival_type, days_from_today, description)
# Ordered by offset so the list reads as a calendar. Offsets are chosen to give
# the recommender a spread of urgent / soon / upcoming festivals on any demo
# date: several inside the 45-day window and a couple outside it.
FESTIVAL_CALENDAR = [
    ('Ganesh Chaturthi', 'other', 6,
     'Birth of Lord Ganesha. Ganesh puja with modak and durva grass.'),
    ('Haritalika Teej', 'teej', 19,
     'Women fast and pray to Lord Shiva for marital wellbeing.'),
    ('Indra Jatra', 'other', 27,
     'Kathmandu Valley chariot festival honouring Lord Indra.'),
    ('Ghatasthapana (Dashain Begins)', 'dashain', 33,
     'The first day of Dashain — jamara is sown at home.'),
    ('Vijaya Dashami', 'dashain', 43,
     'The main day of Dashain. Tika, jamara, and family blessings.'),
    ('Laxmi Puja (Tihar)', 'tihar', 52,
     'Homes are lit with diyo to welcome Goddess Laxmi.'),
    ('Bhai Tika (Tihar)', 'tihar', 55,
     'Sisters apply tika to their brothers. Closing day of Tihar.'),
    ('Chhath Parva', 'chhath', 61,
     'Sun worship on riverbanks, chiefly in the Terai and Kathmandu.'),
    ('Bala Chaturdashi', 'shraddha', 96,
     'Pilgrims offer seeds at Pashupatinath in remembrance of ancestors.'),
    ('Maha Shivaratri', 'shivaratri', 168,
     'The great night of Lord Shiva — the biggest festival at Pashupatinath.'),
]


class Command(BaseCommand):
    help = 'Refresh upcoming festival dates relative to today (idempotent, non-destructive)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--check',
            action='store_true',
            help='Report what would change without writing to the database',
        )

    def handle(self, *args, **options):
        today = timezone.now().date()
        check_only = options['check']
        created_count = 0
        updated_count = 0

        self.stdout.write(f'Today is {today.isoformat()}')

        # Deactivate rows that are in the past and not part of the new calendar.
        stale = UpcomingFestival.objects.filter(date__lt=today, is_active=True)
        stale_names = list(stale.values_list('name', flat=True))
        if stale_names and not check_only:
            stale.update(is_active=False)

        for name, festival_type, offset, description in FESTIVAL_CALENDAR:
            target_date = today + timedelta(days=offset)
            existing = UpcomingFestival.objects.filter(name=name).first()

            if existing is None:
                created_count += 1
                action = 'CREATE'
                if not check_only:
                    UpcomingFestival.objects.create(
                        name=name, festival_type=festival_type,
                        date=target_date, description=description, is_active=True,
                    )
            else:
                changed = (
                    existing.date != target_date
                    or existing.festival_type != festival_type
                    or not existing.is_active
                )
                if changed:
                    updated_count += 1
                    action = 'UPDATE'
                    if not check_only:
                        existing.date = target_date
                        existing.festival_type = festival_type
                        existing.description = description
                        existing.is_active = True
                        existing.save()
                else:
                    action = 'OK    '

            self.stdout.write(
                f'  [{action}] {name:<32} {target_date.isoformat()}  (+{offset}d)'
            )

        if stale_names:
            verb = 'Would deactivate' if check_only else 'Deactivated'
            self.stdout.write(f'  {verb} {len(stale_names)} past festival(s): {", ".join(stale_names)}')

        if check_only:
            self.stdout.write(self.style.WARNING('--check mode: no changes written.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Festival calendar refreshed: {created_count} created, {updated_count} updated.'
            ))
