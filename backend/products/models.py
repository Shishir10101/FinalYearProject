from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.text import slugify


class Area(models.Model):
    """A deliverable area inside the Kathmandu Valley.

    Replaces the hardcoded three-value ``CITY_CHOICES`` enum that was duplicated
    in ``accounts.models`` and ``orders.models``. Keeping it as a table means
    admins can add, rename, or deactivate an area without a code change and a
    migration — which is what "area management" actually requires.

    The ``slug`` values of the three seeded rows are deliberately identical to the
    old enum values (``kathmandu``/``lalitpur``/``bhaktapur``) so existing
    ``Order.shipping_city`` and ``UserProfile.city`` data keeps matching.
    """

    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    district = models.CharField(max_length=50, blank=True, help_text='e.g. Kathmandu')
    delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Override the store-wide delivery fee for this area. Blank = use the default.',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def save(self, *args, **kwargs):
        # Two areas can legitimately share a name, and an admin can retry a
        # create. `slugify` alone would collide on the UNIQUE column and raise
        # IntegrityError, which surfaced as an unhandled 500 from the API.
        # Suffix instead, so a repeated name is still a usable row.
        if not self.slug:
            base = slugify(self.name) or 'area'
            self.slug = base
            counter = 1
            while Area.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Vendor(models.Model):
    """A supplier who lists products on the store.

    Linked 1:1 to a Django ``User`` whose ``UserProfile.role`` is ``vendor``.
    The link is what makes vendor scoping enforceable: a vendor sees only
    ``Product`` rows whose ``vendor`` FK points at their own row.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='vendor',
        help_text='The login account for this vendor.',
    )
    shop_name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    area = models.ForeignKey(
        Area, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vendors',
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['shop_name']

    def save(self, *args, **kwargs):
        # ``slugify`` can return an empty string (e.g. a shop name written
        # entirely in Devanagari, which slugify() strips). Setting ``self.slug``
        # to '' would pass the ``if not self.slug`` guard above but then be
        # re-evaluated on every save, so fall back to a stable, unique value.
        base = slugify(self.shop_name) or f'vendor-{self.user_id or "new"}'
        if not self.slug:
            self.slug = base
            counter = 1
            while Vendor.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.shop_name


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def save(self, *args, **kwargs):
        # Same UNIQUE-slug hazard as Area: a duplicate category name would raise
        # an unhandled IntegrityError. `Category` is also the target of the
        # product-facing admin CRUD, so it must degrade gracefully.
        if not self.slug:
            base = slugify(self.name) or 'category'
            self.slug = base
            counter = 1
            while Category.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base}-{counter}'
                counter += 1
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Product(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, blank=True)
    description = models.TextField()
    # A negative price is not a discount, it is a bug: it would subtract from the
    # cart total. `stock` is a PositiveIntegerField so it is already safe.
    price = models.DecimalField(
        max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
    )
    stock = models.PositiveIntegerField(default=0)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    vendor = models.ForeignKey(
        Vendor, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='products',
        help_text='Supplying vendor. Null for catalogue items with no vendor.',
    )
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    is_featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    popularity_score = models.PositiveIntegerField(default=0)
    unit = models.CharField(max_length=50, default='piece', help_text='e.g., piece, packet, kg, bundle')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-popularity_score', '-created_at']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
            # Ensure unique slug
            counter = 1
            original_slug = self.slug
            while Product.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f"{original_slug}-{counter}"
                counter += 1
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        return self.stock > 0

    def __str__(self):
        return self.name



class Review(models.Model):
    """One customer's rating and comment on one product.

    `docs/DATABASE-DESIGN.md` listed this as a known omission: "No `Coupon` /
    `Review` / `Wishlist` tables — not in scope; noted as post-MVP." Reviews are the
    P1 item that most affects the storefront, because a product page with no social
    proof is the one thing every shopper notices.

    Three deliberate decisions:

    * **One review per customer per product** (`unique_together`). A product page
      where one account can post ten five-star rows is worse than no ratings at all,
      and a unique constraint is the only place that can actually be enforced —
      a UI check is a suggestion.
    * **`is_verified_purchase` is recorded at creation**, not derived at read time.
      It means "this account had ordered this product before writing the review", and
      it has to be a snapshot: deriving it live would let the badge appear or vanish
      as unrelated orders arrive.
    * **`is_approved` defaults to `True`.** Auto-publish with a manager able to hide a
      review afterwards. Pre-moderation would mean every review is invisible until
      someone looks, which on a demo with no staff on duty is indistinguishable from
      the feature not working — and `is_approved=False` is still the mechanism a
      manager uses when something should not be shown.
    """

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='reviews',
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='reviews',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1 to 5 stars.',
    )
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    is_approved = models.BooleanField(
        default=True,
        help_text='Uncheck to hide this review from the storefront without deleting it.',
    )
    is_verified_purchase = models.BooleanField(
        default=False,
        help_text='Set at creation from the reviewer\'s order history. Never recomputed.',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']
        unique_together = ('product', 'user')
        indexes = [
            models.Index(fields=['product', 'is_approved']),
        ]

    def __str__(self):
        return f'{self.product.name} — {self.rating}★ by {self.user.username}'


class WishlistItem(models.Model):
    """A product one customer has saved for later.

    `docs/DATABASE-DESIGN.md` listed this next to `Review` as "not in scope; noted
    as post-MVP". It is the last of that group, and it is a P1 item for a plain
    retail reason: this is a festival-goods shop, so a shopper assembles a list over
    several visits as Dashain or Tihar approaches. Losing that list is losing the
    sale.

    Three deliberate decisions, each mirroring `Review` so the two behave alike:

    * **One row per (user, product)** (`unique_together`). A wishlist with the same
      product five times is not a wishlist. As with reviews, a unique constraint is
      the only place this can actually be enforced — a UI check is a suggestion.
    * **The product FK is `CASCADE`**, unlike `OrderItem`'s snapshot. This is a
      pointer to a live product, not a record of a past transaction: if the product
      is deleted there is nothing left to save, and a dangling wishlist row would
      render as a card that 404s when clicked.
    * **`created_at` orders the list newest-first**, so the thing you just saved is
      at the top rather than buried.
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='wishlist_items',
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name='wishlisted_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']
        unique_together = ('user', 'product')
        indexes = [
            models.Index(fields=['user', '-created_at']),
        ]

    def __str__(self):
        return f'{self.product.name} saved by {self.user.username}'
