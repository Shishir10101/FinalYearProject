from django.db import models
from django.utils.text import slugify
from products.models import Product

FESTIVAL_CHOICES = [
    ('dashain', 'Dashain'),
    ('tihar', 'Tihar'),
    ('shivaratri', 'Maha Shivaratri'),
    ('bratabandha', 'Bratabandha'),
    ('pasni', 'Pasni (Rice Feeding)'),
    ('griha_pravesh', 'Griha Pravesh'),
    ('shraddha', 'Shraddha'),
    ('teej', 'Teej'),
    ('chhath', 'Chhath Puja'),
    ('saraswati', 'Saraswati Puja'),
    ('nag_panchami', 'Nag Panchami'),
    ('janai_purnima', 'Janai Purnima'),
    ('other', 'Other'),
]


class FestivalKit(models.Model):
    name = models.CharField(max_length=200)
    festival_type = models.CharField(max_length=30, choices=FESTIVAL_CHOICES)
    description = models.TextField()
    image = models.ImageField(upload_to='kits/', blank=True, null=True)
    discount_percent = models.PositiveIntegerField(default=0)
    # Which ritual this bundle serves. Nullable so the 7 seeded kits keep working
    # untouched, and SET_NULL so deleting a ritual never deletes a sellable kit.
    puja = models.ForeignKey(
        'Puja', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kits',
        help_text='The ritual this kit is assembled for.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['festival_type', 'name']

    @property
    def total_price(self):
        total = sum(item.product.price * item.quantity for item in self.items.select_related('product'))
        if self.discount_percent > 0:
            total = total * (100 - self.discount_percent) / 100
        return round(total, 2)

    @property
    def original_price(self):
        return sum(item.product.price * item.quantity for item in self.items.select_related('product'))

    def __str__(self):
        return f"{self.name} ({self.get_festival_type_display()})"


class KitItem(models.Model):
    kit = models.ForeignKey(FestivalKit, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('kit', 'product')

    def __str__(self):
        req = "Required" if self.is_required else "Optional"
        return f"{self.product.name} x{self.quantity} ({req})"


class Puja(models.Model):
    """A ritual or ceremony — the fourth discovery entry point.

    ``FESTIVAL_CHOICES`` conflates two different things. It holds ``dashain``,
    ``tihar`` and ``shivaratri``, which are **calendar festivals** that arrive on a
    date, and it also holds ``bratabandha``, ``pasni``, ``griha_pravesh`` and
    ``shraddha``, which are **rites of passage** performed when a family needs
    them rather than when the calendar says so. Two of the enum's own labels even
    end in "Puja" (``chhath`` → "Chhath Puja", ``saraswati`` → "Saraswati Puja").

    So a ``Puja`` is the ritual, and a ``FestivalKit`` is one purchasable bundle
    that serves it. They are deliberately separate because they answer different
    questions — *"what does this ritual need?"* versus *"what can I buy in one
    click?"* — and because a puja can exist before anyone has assembled a kit for
    it, which is the normal state of affairs.

    ``AGENTS.md`` §1 requires discovery through six entry points
    (Product · Category · Festival · **Puja** · Samagri · Ready-made Kit). The
    Puja entry point had no model, endpoint or page until this was added.
    """

    name = models.CharField(max_length=120)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    occasion_type = models.CharField(
        max_length=30, choices=FESTIVAL_CHOICES, blank=True,
        help_text='Optional link to the same vocabulary kits and the calendar use.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'Pujas'

    def save(self, *args, **kwargs):
        # Same UNIQUE-slug hazard as Product / Area / Category / Vendor: a repeated
        # name (or an admin retrying a create) must not raise an unhandled
        # IntegrityError, which the API surfaced as HTTP 500. `slugify()` can also
        # return '' for a fully non-Latin name, so there is a fallback.
        if not self.slug:
            base = slugify(self.name) or 'puja'
            self.slug = base
            counter = 1
            while Puja.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @property
    def required_items(self):
        return self.items.filter(is_required=True)

    @property
    def kit(self):
        """The first active ready-made kit for this ritual, if one exists.

        Written as a loop over ``self.kits.all()`` rather than
        ``self.kits.filter(...)`` on purpose: ``.filter()`` on a related manager
        bypasses the prefetch cache and issues a fresh query, which turns a list
        endpoint into one query per row. ``.all()`` reuses the cache.
        """
        for kit in self.kits.all():
            if kit.is_active:
                return kit
        return None


class PujaItem(models.Model):
    """One product a ritual calls for, and whether it is essential.

    ``is_required`` is the same required-samagri distinction ``KitItem`` makes.
    The two lists are not redundant: a kit is a bundle a shop chooses to sell, and
    its optional extras are a merchandising decision, whereas a puja's list is the
    ritual requirement. Today the seeded pujas take their lists from the project's
    own kit data, so the two agree — that is a seeding choice, not a constraint.
    """

    puja = models.ForeignKey(Puja, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('puja', 'product')
        # Required first, then a stable tiebreak so ordering is deterministic.
        ordering = ['-is_required', 'id']

    def __str__(self):
        req = "Required" if self.is_required else "Optional"
        return f"{self.product.name} x{self.quantity} ({req})"


class UpcomingFestival(models.Model):
    """Track upcoming festivals with dates for smart predictions"""
    name = models.CharField(max_length=100)
    festival_type = models.CharField(max_length=30, choices=FESTIVAL_CHOICES)
    date = models.DateField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.name} - {self.date}"
