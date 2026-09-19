"""Tests for the explainable recommendation engine.

Run with::

    python manage.py test festivals -v 2

These tests exist because the *previous* implementation had a silent
correctness bug: it collected candidate products into a ``set()`` and sliced it,
which destroys any ranking. A test that only asserted "we got 12 products back"
would have passed against the broken code. These tests assert ordering and
explanation, which the broken code could not satisfy.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from products.models import Category, Product
from .models import FestivalKit, KitItem, UpcomingFestival
from .recommender import (
    WEIGHTS,
    RECOMMENDATION_WINDOW_DAYS,
    Recommender,
)


class RecommenderTestCase(TestCase):
    def setUp(self):
        self.today = timezone.now().date()

        self.cat_flower = Category.objects.create(name='Puja Flowers')
        self.cat_vessel = Category.objects.create(name='Puja Vessels')

        self.marigold = Product.objects.create(
            name='Marigold Garland', description='x', price=Decimal('200'),
            stock=50, category=self.cat_flower, popularity_score=10,
        )
        self.diyo = Product.objects.create(
            name='Brass Diyo', description='x', price=Decimal('250'),
            stock=50, category=self.cat_vessel, popularity_score=20,
        )
        self.bell = Product.objects.create(
            name='Puja Bell', description='x', price=Decimal('280'),
            stock=50, category=self.cat_vessel, popularity_score=30,
        )
        self.unrelated = Product.objects.create(
            name='Random Book', description='x', price=Decimal('100'),
            stock=50, category=self.cat_vessel, popularity_score=99,
        )
        self.out_of_stock = Product.objects.create(
            name='Sold Out Item', description='x', price=Decimal('100'),
            stock=0, category=self.cat_flower, popularity_score=100,
        )
        self.inactive = Product.objects.create(
            name='Inactive Item', description='x', price=Decimal('100'),
            stock=50, category=self.cat_flower, is_active=False,
        )

    def _make_dashain_kit(self, days_away=5):
        festival = UpcomingFestival.objects.create(
            name='Vijaya Dashami', festival_type='dashain',
            date=self.today + timedelta(days=days_away),
        )
        kit = FestivalKit.objects.create(
            name='Dashain Kit', festival_type='dashain', description='x',
        )
        KitItem.objects.create(kit=kit, product=self.marigold, quantity=1, is_required=True)
        KitItem.objects.create(kit=kit, product=self.bell, quantity=1, is_required=False)
        return festival, kit

    # -- ordering ----------------------------------------------------------

    def test_required_item_outranks_optional_item(self):
        """A required samagri must beat an optional extra from the same kit."""
        self._make_dashain_kit()
        result = Recommender(user=None, today=self.today).build(limit=10)
        ranked = [e.product.name for e in result['recommended_products']]

        self.assertIn('Marigold Garland', ranked)
        self.assertIn('Puja Bell', ranked)
        self.assertLess(
            ranked.index('Marigold Garland'), ranked.index('Puja Bell'),
            'Required kit item should rank above the optional one',
        )

    def test_festival_items_outrank_unrelated_popular_item(self):
        """Domain signal must beat raw popularity.

        ``Random Book`` has the highest popularity_score in the fixture (99) but
        is in no upcoming festival kit. The old implementation would have let it
        win; the ranker must not.
        """
        self._make_dashain_kit()
        result = Recommender(user=None, today=self.today).build(limit=10)
        ranked = [e.product.name for e in result['recommended_products']]

        self.assertLess(
            ranked.index('Marigold Garland'), ranked.index('Random Book'),
            'Festival-required item must outrank an unrelated popular item',
        )

    def test_ranking_is_deterministic(self):
        """Same inputs -> identical order. The set()-based code could not do this."""
        self._make_dashain_kit()

        def order():
            return [
                e.product.id
                for e in Recommender(user=None, today=self.today).build(12)['recommended_products']
            ]

        first = order()
        self.assertTrue(first)
        for _ in range(5):
            self.assertEqual(first, order(), 'Recommendation order must be stable')

    def test_sooner_festival_is_preferred(self):
        """Given equal kit membership, the nearer festival should not lose."""
        soon = UpcomingFestival.objects.create(
            name='Soon Fest', festival_type='teej',
            date=self.today + timedelta(days=2),
        )
        later = UpcomingFestival.objects.create(
            name='Later Fest', festival_type='tihar',
            date=self.today + timedelta(days=40),
        )
        soon_kit = FestivalKit.objects.create(name='Soon Kit', festival_type='teej', description='x')
        KitItem.objects.create(kit=soon_kit, product=self.marigold, quantity=1, is_required=True)
        later_kit = FestivalKit.objects.create(name='Later Kit', festival_type='tihar', description='x')
        KitItem.objects.create(kit=later_kit, product=self.diyo, quantity=1, is_required=True)

        result = Recommender(user=None, today=self.today).build(10)
        by_name = {e.product.name: e for e in result['recommended_products']}

        self.assertEqual(by_name['Marigold Garland'].days_until, 2)
        self.assertEqual(by_name['Marigold Garland'].urgency, 'urgent')
        self.assertEqual(by_name['Brass Diyo'].urgency, 'upcoming')

    # -- explanations ------------------------------------------------------

    def test_every_recommendation_has_a_reason(self):
        """No black-box recommendations: each entry must explain itself."""
        self._make_dashain_kit()
        result = Recommender(user=None, today=self.today).build(10)

        self.assertTrue(result['recommended_products'])
        for entry in result['recommended_products']:
            self.assertGreater(entry.score, 0, f'{entry.product.name} scored 0')
            self.assertTrue(entry.reasons, f'{entry.product.name} has no reason')
            for reason in entry.reasons:
                self.assertIn('code', reason)
                self.assertIn('text', reason)
                self.assertGreater(reason['points'], 0)
                self.assertTrue(reason['text'].strip())

    def test_score_equals_sum_of_reason_points(self):
        """Scores must be fully decomposable into the reasons we show."""
        self._make_dashain_kit()
        result = Recommender(user=None, today=self.today).build(10)
        for entry in result['recommended_products']:
            self.assertEqual(
                entry.score, sum(r['points'] for r in entry.reasons),
                f'{entry.product.name} score does not match its reasons',
            )

    def test_reason_mentions_festival_and_days(self):
        self._make_dashain_kit(days_away=5)
        result = Recommender(user=None, today=self.today).build(10)
        entry = next(e for e in result['recommended_products'] if e.product.name == 'Marigold Garland')

        self.assertEqual(entry.festival_name, 'Vijaya Dashami')
        self.assertEqual(entry.days_until, 5)
        codes = {r['code'] for r in entry.reasons}
        self.assertIn('festival_required', codes)
        text = ' '.join(r['text'] for r in entry.reasons)
        self.assertIn('Vijaya Dashami', text)
        self.assertIn('5 days', text)

    # -- filtering ---------------------------------------------------------

    def test_excludes_out_of_stock_and_inactive(self):
        self._make_dashain_kit()
        result = Recommender(user=None, today=self.today).build(50)
        names = {e.product.name for e in result['recommended_products']}

        self.assertNotIn('Sold Out Item', names)
        self.assertNotIn('Inactive Item', names)

    def test_festival_outside_window_contributes_nothing(self):
        """A festival beyond the window must not create festival-required reasons."""
        far = self.today + timedelta(days=RECOMMENDATION_WINDOW_DAYS + 30)
        UpcomingFestival.objects.create(
            name='Far Fest', festival_type='dashain', date=far,
        )
        kit = FestivalKit.objects.create(name='Far Kit', festival_type='dashain', description='x')
        KitItem.objects.create(kit=kit, product=self.marigold, quantity=1, is_required=True)

        result = Recommender(user=None, today=self.today).build(50)
        entry = next(
            (e for e in result['recommended_products'] if e.product.name == 'Marigold Garland'),
            None,
        )
        if entry is not None:
            codes = {r['code'] for r in entry.reasons}
            self.assertNotIn('festival_required', codes)

    def test_inactive_festival_is_ignored(self):
        festival, kit = self._make_dashain_kit()
        festival.is_active = False
        festival.save()

        result = Recommender(user=None, today=self.today).build(50)
        names = {e.product.name for e in result['recommended_products']}
        # Marigold may still appear via popularity, but never as festival_required.
        entry = next((e for e in result['recommended_products'] if e.product.name == 'Marigold Garland'), None)
        if entry is not None:
            self.assertNotIn('festival_required', {r['code'] for r in entry.reasons})

    def test_limit_is_respected(self):
        self._make_dashain_kit()
        for limit in (1, 3, 5):
            result = Recommender(user=None, today=self.today).build(limit=limit)
            self.assertLessEqual(len(result['recommended_products']), limit)

    # -- staple samagri signal ---------------------------------------------

    def test_staple_signal_fires_for_kitless_festival(self):
        """A festival with no curated kit must still drive recommendations.

        Ganesh Chaturthi / Indra Jatra have no FestivalKit in the catalogue, so
        without the staple signal the most imminent festival would be invisible.
        """
        UpcomingFestival.objects.create(
            name='Ganesh Chaturthi', festival_type='other',
            date=self.today + timedelta(days=6),
        )
        # marigold sits in a STAPLE_CATEGORIES-style category name
        self.cat_flower.name = 'Puja Flowers & Garlands'
        self.cat_flower.save()

        result = Recommender(user=None, today=self.today).build(50)
        entry = next(
            (e for e in result['recommended_products'] if e.product.id == self.marigold.id),
            None,
        )
        self.assertIsNotNone(entry, 'Staple item should be recommended')
        codes = {r['code'] for r in entry.reasons}
        self.assertIn('staple_samagri', codes)
        self.assertEqual(entry.days_until, 6)
        self.assertEqual(entry.festival_name, 'Ganesh Chaturthi')

    def test_staple_signal_silent_when_no_festival_is_close(self):
        """Staple boost only applies inside STAPLE_WINDOW_DAYS."""
        UpcomingFestival.objects.create(
            name='Far Fest', festival_type='other',
            date=self.today + timedelta(days=RECOMMENDATION_WINDOW_DAYS),
        )
        self.cat_flower.name = 'Puja Flowers & Garlands'
        self.cat_flower.save()

        result = Recommender(user=None, today=self.today).build(50)
        entry = next(
            (e for e in result['recommended_products'] if e.product.id == self.marigold.id),
            None,
        )
        if entry is not None:
            self.assertNotIn('staple_samagri', {r['code'] for r in entry.reasons})

    def test_curated_kit_festival_badge_wins_over_staple(self):
        """A specific kit association must not be overwritten by the staple rule."""
        self.cat_flower.name = 'Puja Flowers & Garlands'
        self.cat_flower.save()
        # Dashain kit at 33 days (outside staple window) + a near kitless festival
        _, _ = self._make_dashain_kit(days_away=33)
        UpcomingFestival.objects.create(
            name='Ganesh Chaturthi', festival_type='other',
            date=self.today + timedelta(days=6),
        )

        result = Recommender(user=None, today=self.today).build(50)
        entry = next(e for e in result['recommended_products'] if e.product.id == self.marigold.id)
        self.assertEqual(
            entry.festival_name, 'Vijaya Dashami',
            'Curated kit association should take precedence for the badge',
        )

    def test_staple_ranks_below_required_kit_item(self):
        """Universal staples must not outrank an explicitly required samagri."""
        self.cat_flower.name = 'Puja Flowers & Garlands'
        self.cat_flower.save()
        self._make_dashain_kit(days_away=33)
        UpcomingFestival.objects.create(
            name='Ganesh Chaturthi', festival_type='other',
            date=self.today + timedelta(days=6),
        )

        result = Recommender(user=None, today=self.today).build(50)
        by_name = {e.product.name: e.score for e in result['recommended_products']}
        self.assertGreater(
            by_name['Marigold Garland'], by_name['Brass Diyo'],
            'Festival-required item must beat a staple-boosted item',
        )

    # -- personalisation ---------------------------------------------------

    def test_personalisation_boosts_previously_ordered_product(self):
        """A past purchase must be surfaced with an explicit reason."""
        user = User.objects.create_user('shopper', password='pw123456')
        from orders.models import Order, OrderItem

        order = Order.objects.create(
            user=user, total_amount=Decimal('250'), shipping_address='x',
            shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=order, product=self.diyo, product_name=self.diyo.name,
            quantity=1, price=self.diyo.price,
        )

        anon = Recommender(user=None, today=self.today).build(50)
        personalised = Recommender(user=user, today=self.today).build(50)

        anon_scores = {e.product.id: e.score for e in anon['recommended_products']}
        pers_scores = {e.product.id: e.score for e in personalised['recommended_products']}

        self.assertIn(self.diyo.id, pers_scores)
        self.assertGreater(
            pers_scores[self.diyo.id], anon_scores.get(self.diyo.id, 0),
            'Past purchase should raise the score',
        )

        entry = next(e for e in personalised['recommended_products'] if e.product.id == self.diyo.id)
        codes = {r['code'] for r in entry.reasons}
        self.assertIn('user_repeat', codes)
        self.assertIn('user_category', codes)

    def test_anonymous_user_is_not_personalised(self):
        result = Recommender(user=None, today=self.today).build(10)
        self.assertFalse(result['meta']['personalised'])

    def test_meta_reports_algorithm(self):
        self._make_dashain_kit()
        meta = Recommender(user=None, today=self.today).build(10)['meta']
        self.assertEqual(meta['algorithm'], 'weighted-signal-ranker')
        self.assertEqual(meta['window_days'], RECOMMENDATION_WINDOW_DAYS)
        self.assertIn('candidate_count', meta)


class RecommendationEndpointTestCase(TestCase):
    """The HTTP contract the frontend depends on."""

    def setUp(self):
        self.today = timezone.now().date()
        cat = Category.objects.create(name='Puja Flowers')
        self.product = Product.objects.create(
            name='Marigold Garland', description='x', price=Decimal('200'),
            stock=10, category=cat, popularity_score=50,
        )
        festival = UpcomingFestival.objects.create(
            name='Vijaya Dashami', festival_type='dashain',
            date=self.today + timedelta(days=4),
        )
        kit = FestivalKit.objects.create(name='K', festival_type='dashain', description='x')
        KitItem.objects.create(kit=kit, product=self.product, quantity=1, is_required=True)

    def test_endpoint_returns_ranked_explainable_payload(self):
        response = self.client.get('/api/festivals/recommendations/')
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn('upcoming_festivals', data)
        self.assertIn('recommended_products', data)
        self.assertIn('meta', data)

        first = data['recommended_products'][0]
        self.assertEqual(first['name'], 'Marigold Garland')
        self.assertIn('recommendation', first)
        self.assertGreater(first['recommendation']['score'], 0)
        self.assertTrue(first['recommendation']['reasons'])

    def test_endpoint_is_public(self):
        response = self.client.get('/api/festivals/recommendations/')
        self.assertEqual(response.status_code, 200)

    def test_limit_query_param(self):
        response = self.client.get('/api/festivals/recommendations/?limit=1')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()['recommended_products']), 1)

    def test_invalid_limit_falls_back(self):
        response = self.client.get('/api/festivals/recommendations/?limit=abc')
        self.assertEqual(response.status_code, 200)

    def test_upcoming_endpoint_now_returns_future_festivals(self):
        response = self.client.get('/api/festivals/upcoming/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(len(response.json()) > 0, 'Festival calendar should not be empty')


class UpcomingFestivalsLimitTests(TestCase):
    """`/festivals/upcoming/` used to be hardcoded to `[:5]`.

    With ten active future festivals in the database, five of them were
    unreachable through the API and nothing said so — the storefront and the home
    page both silently showed the first five. The cap is now a query parameter, so
    a caller that wants the whole calendar can ask for it.
    """

    def setUp(self):
        self.today = timezone.now().date()
        UpcomingFestival.objects.all().delete()
        for i in range(1, 13):
            UpcomingFestival.objects.create(
                name=f'Festival {i}',
                festival_type='other',
                date=self.today + timedelta(days=i * 5),
                description='x',
                is_active=True,
            )
        # A past festival must never appear.
        UpcomingFestival.objects.create(
            name='Already Happened', festival_type='other',
            date=self.today - timedelta(days=3), description='x', is_active=True,
        )

    def test_default_returns_five(self):
        response = self.client.get('/api/festivals/upcoming/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 5)

    def test_limit_returns_the_whole_calendar(self):
        response = self.client.get('/api/festivals/upcoming/?limit=12')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 12)

    def test_results_are_soonest_first(self):
        dates = [f['date'] for f in self.client.get('/api/festivals/upcoming/?limit=5').json()]
        self.assertEqual(dates, sorted(dates), 'the calendar must read soonest-first')

    def test_past_festivals_are_never_returned(self):
        names = [f['name'] for f in self.client.get('/api/festivals/upcoming/?limit=50').json()]
        self.assertNotIn('Already Happened', names)

    def test_limit_is_capped(self):
        """An unbounded limit would let a caller dump the whole table."""
        response = self.client.get('/api/festivals/upcoming/?limit=9999')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.json()), 50)

    def test_limit_floor_is_one(self):
        response = self.client.get('/api/festivals/upcoming/?limit=0')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 1)

    def test_invalid_limit_falls_back_to_default(self):
        response = self.client.get('/api/festivals/upcoming/?limit=abc')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()), 5)
