"""Explainable recommendation engine for Puja Samagri.

Design goals
------------
1. **Domain-first.** A generic "popular items" list is worthless here. The signal
   that actually matters is *what ritual is coming up, and which samagri does that
   ritual require?* That is the whole reason this is not a Daraz clone.
2. **Ranked.** The previous implementation collected candidate product IDs into a
   Python ``set()`` and sliced it. Set iteration order is arbitrary, so the
   "recommendation" was effectively random and no score existed at all.
3. **Explainable.** Every recommendation carries a machine-readable ``reason``
   code *and* a human sentence, so the UI can show the customer why they are
   seeing an item. An unexplainable recommendation is a black box.
4. **Testable.** All logic lives in :class:`Recommender`, a plain class with no
   HTTP or ORM-view coupling, so it can be unit-tested directly.

Scoring model
-------------
Each candidate product accumulates points from independent signals. Signals are
additive so the total is always decomposable back into the reasons shown to the
user. Weights live in :data:`WEIGHTS` — a single place to tune, and the numbers
are reproduced verbatim in ``docs/AI-RECOMMENDATION.md``.

The score is intentionally *not* normalised to 0..1. A raw integer is easier to
debug and the reasons block tells the user far more than a percentage would.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from django.utils import timezone

from products.models import Product

# ---------------------------------------------------------------------------
# Weights — every point awarded must be traceable to one of these constants.
# ---------------------------------------------------------------------------

WEIGHTS = {
    # A festival is approaching and this product is a REQUIRED item of a kit for
    # that festival. Strongest possible intent signal.
    'festival_required': 60,
    # Same festival, but the item is optional in the kit.
    'festival_optional': 30,
    # Nithya samagri: items used in essentially every Hindu ritual in the valley
    # (diyo, batti, dhoop, sindoor, kalava...). These matter most when a festival
    # is close, because the household is about to run a full puja. Without this
    # signal a festival that has no curated kit (e.g. Ganesh Chaturthi) would
    # contribute nothing even when it is days away.
    'staple_samagri': 28,
    # Product belongs to a category that the user has bought from before.
    'user_category': 22,
    # Product sits in the same kit as something the user already bought.
    'user_kit_affinity': 16,
    # The user has ordered this exact product before -> repurchase nudge.
    'user_repeat': 14,
    # Falls back on catalogue popularity, scaled by popularity_score.
    'popularity_base': 8,
    'popularity_max': 12,
}

# Categories whose products are considered nithya (daily/universal) samagri.
# Matched against Category.name, which is the stable identifier used by the
# seeder and the admin UI.
STAPLE_CATEGORIES = frozenset({
    'Dhoop & Agarbatti',
    'Tika & Sindoor',
    'Puja Flowers & Garlands',
    'Sacred Threads',
    'Puja Oils & Ghee',
    'Offerings & Prasad',
})

# A festival further out than this contributes nothing — recommending Tihar
# samagri nine months early is noise.
RECOMMENDATION_WINDOW_DAYS = 45

# Staple samagri only gets its boost while a festival is at least this close.
# Beyond that it is just ordinary inventory.
STAPLE_WINDOW_DAYS = 21

# How many days back to look when learning the user's taste.
HISTORY_WINDOW_DAYS = 365

# Urgency buckets, expressed in days-until-festival.
URGENT_DAYS = 7
SOON_DAYS = 21


@dataclass
class ScoredProduct:
    """A product plus the evidence for why it was recommended."""

    product: Product
    score: int = 0
    reasons: list = field(default_factory=list)
    # Populated when the festival signal fires; drives the UI badge.
    festival_name: str | None = None
    festival_type: str | None = None
    days_until: int | None = None

    def add(self, points, code, text):
        """Award points and record the corresponding human-readable reason."""
        if points <= 0:
            return
        self.score += points
        self.reasons.append({'code': code, 'points': points, 'text': text})

    @property
    def urgency(self):
        """Coarse urgency label used for sorting ties and for UI colour."""
        if self.days_until is None:
            return None
        if self.days_until <= URGENT_DAYS:
            return 'urgent'
        if self.days_until <= SOON_DAYS:
            return 'soon'
        return 'upcoming'


class Recommender:
    """Builds a ranked, explainable product list for a shopper.

    Usage::

        rec = Recommender(user=request.user)
        payload = rec.build(limit=12)

    ``user`` may be ``None`` or an anonymous user — the engine then simply skips
    the personalisation signals and ranks on festival + popularity alone, which
    is the correct behaviour for a logged-out visitor.
    """

    def __init__(self, user=None, today=None):
        self.user = user if getattr(user, 'is_authenticated', False) else None
        self.today = today or timezone.now().date()

    # -- public API ---------------------------------------------------------

    def upcoming_festivals(self):
        """Active festivals inside the recommendation window, soonest first."""
        from .models import UpcomingFestival

        return list(
            UpcomingFestival.objects.filter(
                date__gte=self.today,
                date__lte=self.today + timedelta(days=RECOMMENDATION_WINDOW_DAYS),
                is_active=True,
            ).order_by('date')
        )

    def build(self, limit=12):
        """Return the response payload: festivals + ranked products."""
        festivals = self.upcoming_festivals()
        scored = {}

        # Signal 1+2 — festival kits (the domain-specific core).
        self._apply_festival_signal(festivals, scored)

        # Signal 3 — nithya samagri while a festival is close.
        self._apply_staple_signal(festivals, scored)

        # Signal 4+5+6 — personalisation from order history.
        if self.user is not None:
            self._apply_user_signal(scored)

        # Signal 7 — popularity backstop so the list is never thin.
        self._apply_popularity_signal(scored)

        ranked = self._rank(scored, limit)

        return {
            'upcoming_festivals': festivals,
            'recommended_products': ranked,
            'meta': {
                'algorithm': 'weighted-signal-ranker',
                'version': 1,
                'window_days': RECOMMENDATION_WINDOW_DAYS,
                'personalised': self.user is not None,
                'candidate_count': len(scored),
            },
        }

    # -- signals ------------------------------------------------------------

    def _apply_festival_signal(self, festivals, scored):
        """Award points to every samagri required by an approaching festival."""
        from .models import FestivalKit

        for festival in festivals:
            days_until = (festival.date - self.today).days
            kits = (
                FestivalKit.objects.filter(
                    festival_type=festival.festival_type, is_active=True
                )
                .prefetch_related('items__product')
            )
            for kit in kits:
                for item in kit.items.all():
                    product = item.product
                    if not product.is_active or not product.in_stock:
                        continue

                    entry = scored.get(product.id)
                    if entry is None:
                        entry = ScoredProduct(product=product)
                        scored[product.id] = entry

                    # Only the *soonest* festival may set the badge, otherwise a
                    # later festival would overwrite a more urgent one.
                    is_first_festival = (
                        entry.festival_type is None
                        or days_until < (entry.days_until or 10**6)
                    )
                    if is_first_festival:
                        entry.festival_name = festival.name
                        entry.festival_type = festival.festival_type
                        entry.days_until = days_until

                    if item.is_required:
                        entry.add(
                            WEIGHTS['festival_required'],
                            'festival_required',
                            f'Required for {festival.name} ({days_until} days away)',
                        )
                    else:
                        entry.add(
                            WEIGHTS['festival_optional'],
                            'festival_optional',
                            f'Optional extra for {festival.name}',
                        )

    def _apply_staple_signal(self, festivals, scored):
        """Boost universal (nithya) samagri while a festival is imminent.

        Rationale: some festivals — Ganesh Chaturthi, Indra Jatra, Chhath — have
        no curated kit in the catalogue, so the kit-based signal is blind to
        them. But when Ganesh Chaturthi is six days out, a Kathmandu household
        genuinely does need diyo, batti, dhoop and sindoor. This signal captures
        that with an explicit, auditable rule rather than by fudging weights.
        """
        imminent = [f for f in festivals if (f.date - self.today).days <= STAPLE_WINDOW_DAYS]
        if not imminent:
            return

        # Name the nearest one — that is what the customer cares about.
        nearest = min(imminent, key=lambda f: f.date)
        days_until = (nearest.date - self.today).days

        staples = Product.objects.filter(
            is_active=True,
            stock__gt=0,
            category__name__in=STAPLE_CATEGORIES,
        ).select_related('category').order_by('-popularity_score')[:12]

        for product in staples:
            entry = scored.get(product.id)
            if entry is None:
                entry = ScoredProduct(product=product)
                scored[product.id] = entry

            entry.add(
                WEIGHTS['staple_samagri'],
                'staple_samagri',
                f'Everyday puja essential — needed for {nearest.name} in {days_until} days',
            )
            # Only adopt the festival badge if this product had no festival yet;
            # a curated kit association is more specific and must win.
            if entry.festival_type is None:
                entry.festival_name = nearest.name
                entry.festival_type = nearest.festival_type
                entry.days_until = days_until

    def _apply_user_signal(self, scored):
        """Award points based on what this shopper has bought before."""
        from orders.models import OrderItem

        history = (
            OrderItem.objects.filter(
                order__user=self.user,
                order__created_at__date__gte=self.today - timedelta(days=HISTORY_WINDOW_DAYS),
            )
            .select_related('product', 'product__category')
            .exclude(product__isnull=True)
        )
        if not history:
            return

        purchased_ids = set()
        category_ids = set()
        for item in history:
            purchased_ids.add(item.product_id)
            category_ids.add(item.product.category_id)

        # Same kit membership as anything previously bought -> strong affinity.
        from .models import KitItem

        kit_ids = set(
            KitItem.objects.filter(product_id__in=purchased_ids).values_list(
                'kit_id', flat=True
            )
        )
        affinity_ids = set()
        if kit_ids:
            affinity_ids = set(
                KitItem.objects.filter(kit_id__in=kit_ids)
                .exclude(product_id__in=purchased_ids)
                .values_list('product_id', flat=True)
            )

        # Resolve the actual sellable product ids we are allowed to show.
        candidate_ids = set(
            Product.objects.filter(
                is_active=True, stock__gt=0
            ).filter(id__in=affinity_ids | purchased_ids).values_list('id', flat=True)
        )
        # Category affinity applies broadly, so resolve those separately.
        category_product_ids = set(
            Product.objects.filter(
                is_active=True, stock__gt=0, category_id__in=category_ids
            ).values_list('id', flat=True)
        )

        all_ids = candidate_ids | category_product_ids
        for product in Product.objects.filter(id__in=all_ids, is_active=True, stock__gt=0):
            entry = scored.get(product.id)
            if entry is None:
                entry = ScoredProduct(product=product)
                scored[product.id] = entry

            if product.id in affinity_ids:
                entry.add(
                    WEIGHTS['user_kit_affinity'],
                    'user_kit_affinity',
                    'Goes with items you have bought before',
                )
            if product.id in purchased_ids:
                entry.add(
                    WEIGHTS['user_repeat'],
                    'user_repeat',
                    'You have ordered this before',
                )
            if product.category_id in category_ids:
                entry.add(
                    WEIGHTS['user_category'],
                    'user_category',
                    f'You often buy from {product.category.name}',
                )

    def _apply_popularity_signal(self, scored):
        """Ensure the catalogue's best sellers are always in the pool."""
        for product in Product.objects.filter(is_active=True, stock__gt=0).order_by(
            '-popularity_score', '-created_at'
        )[:20]:
            entry = scored.get(product.id)
            if entry is None:
                entry = ScoredProduct(product=product)
                scored[product.id] = entry
            # Scale popularity into a small band so it never outranks a real
            # festival requirement, but does break ties sensibly.
            bonus = min(
                WEIGHTS['popularity_max'],
                WEIGHTS['popularity_base'] + product.popularity_score // 4,
            )
            entry.add(bonus, 'popular', f'Popular item (score {product.popularity_score})')

    # -- ranking ------------------------------------------------------------

    def _rank(self, scored, limit):
        """Sort by score, then urgency, then popularity, then id (stable)."""
        urgency_rank = {'urgent': 0, 'soon': 1, 'upcoming': 2, None: 3}
        ordered = sorted(
            scored.values(),
            key=lambda s: (
                -s.score,
                urgency_rank.get(s.urgency, 3),
                -s.product.popularity_score,
                s.product.id,
            ),
        )
        return ordered[:limit]


def serialize_recommendations(entries, serializer_class):
    """Attach explanation metadata to serialized product dicts.

    Kept separate from :class:`Recommender` so the ranking logic has no
    dependency on DRF serializers.
    """
    out = []
    for entry in entries:
        data = serializer_class(entry.product).data
        data['recommendation'] = {
            'score': entry.score,
            'urgency': entry.urgency,
            'festival_name': entry.festival_name,
            'festival_type': entry.festival_type,
            'days_until': entry.days_until,
            'reasons': entry.reasons,
        }
        out.append(data)
    return out
