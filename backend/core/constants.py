"""Shared domain constants.

``CITY_CHOICES`` used to be defined twice — once in ``accounts.models`` and once
in ``orders.models`` — with identical contents. Two copies of the same enum drift;
this module is the single source of truth.
"""

# The three districts of the Kathmandu Valley. Used for delivery areas and
# customer addresses.
CITY_CHOICES = [
    ('kathmandu', 'Kathmandu'),
    ('lalitpur', 'Lalitpur'),
    ('bhaktapur', 'Bhaktapur'),
]

CITY_SLUGS = [slug for slug, _label in CITY_CHOICES]
