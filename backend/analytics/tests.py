"""Tests for the demand-forecasting engine.

Two questions these tests must answer:

1. **Is the model real?** Not "does it run" — a constant would run. The tests
   verify it recovers structure it was never told about (weekday seasonality, a
   trend) and that it beats a naive baseline out-of-sample.
2. **Is the provenance honest?** The dataset is synthetic. The tests assert that
   every response says so, so it can never be silently presented as real demand.
"""

import math
import random
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from analytics.forecasting import (
    SeasonalForecaster,
    build_synthetic_history,
    _mean,
    _median,
)
from analytics.models import SyntheticSalesRecord


class StatsHelperTests(TestCase):
    def test_median_odd_and_even(self):
        self.assertEqual(_median([3, 1, 2]), 2)
        self.assertEqual(_median([4, 1, 3, 2]), 2.5)
        self.assertEqual(_median([]), 0.0)

    def test_mean(self):
        self.assertEqual(_mean([1, 2, 3]), 2)
        self.assertEqual(_mean([]), 0.0)


class SeasonalForecasterTests(TestCase):
    """Verify the model learns real structure from synthetic data."""

    def _generate(self, days=300, seed=1234):
        """Flat weekday-pattern series with a known Saturday spike."""
        rng = random.Random(seed)
        start = date(2025, 1, 1)
        weights = {0: 1.0, 1: 1.0, 2: 1.0, 3: 1.0, 4: 1.0, 5: 3.0, 6: 1.0}
        series = {}
        for i in range(days):
            day = start + timedelta(days=i)
            base = 20.0 * weights[day.weekday()]
            series[day] = max(0, int(round(base * rng.gauss(1.0, 0.05))))
        return series

    def test_learns_saturday_spike(self):
        """A 3x Saturday spike must be recovered without being told the pattern."""
        series = self._generate()
        forecaster = SeasonalForecaster().fit(series)

        factors = forecaster.weekday_factors
        self.assertEqual(max(factors, key=factors.get), 5,
                         'Saturday should be the highest-demand weekday')
        self.assertGreater(factors[5], factors[0] * 2.0)
        self.assertLess(factors[0], 1.2)

    def test_learns_upward_trend(self):
        """A rising series must produce a positive slope."""
        start = date(2025, 1, 1)
        series = {
            start + timedelta(days=i): 10 + i * 0.5
            for i in range(120)
        }
        forecaster = SeasonalForecaster().fit(series)
        self.assertGreater(forecaster.trend_slope, 0)

    def test_learns_downward_trend(self):
        start = date(2025, 1, 1)
        series = {
            start + timedelta(days=i): max(0, 100 - i * 0.5)
            for i in range(120)
        }
        forecaster = SeasonalForecaster().fit(series)
        self.assertLess(forecaster.trend_slope, 0)

    def test_beats_naive_baseline_out_of_sample(self):
        """The model must beat 'predict the training mean' on unseen days.

        This is the test that separates a real model from a constant.
        """
        series = self._generate(days=320)
        forecaster = SeasonalForecaster()
        metrics = forecaster.evaluate(series, holdout_days=28)

        ordered = sorted(series.items())
        train = ordered[:-28]
        test = ordered[-28:]
        train_mean = _mean([u for _, u in train])
        naive_mae = _mean([abs(train_mean - u) for _, u in test])

        self.assertIsNotNone(metrics['mae'])
        self.assertLess(
            metrics['mae'], naive_mae,
            f"Model MAE {metrics['mae']} should beat naive MAE {naive_mae:.3f}",
        )

    def test_mape_is_reported_from_holdout(self):
        series = self._generate(days=200)
        metrics = SeasonalForecaster().evaluate(series, holdout_days=28)

        self.assertEqual(metrics['holdout_days'], 28)
        self.assertIsNotNone(metrics['mape'])
        self.assertGreater(metrics['mape'], 0)
        self.assertLess(metrics['mape'], 200)  # sanity: not catastrophically wrong

    def test_evaluation_flags_insufficient_history(self):
        series = {date(2025, 1, 1) + timedelta(days=i): 5 for i in range(10)}
        metrics = SeasonalForecaster().evaluate(series, holdout_days=28)
        self.assertEqual(metrics['holdout_days'], 0)
        self.assertIsNone(metrics['mape'])

    def test_festival_term_raises_forecast_before_festival(self):
        """The calendar term must lift predictions as a festival approaches."""
        series = {date(2025, 1, 1) + timedelta(days=i): 10 for i in range(200)}
        festival_day = date(2025, 7, 1)

        with_festival = SeasonalForecaster(festival_dates=[('dashain', festival_day)])
        with_festival.fit(series)
        preds = with_festival.predict(festival_day - timedelta(days=20), 1)

        without = SeasonalForecaster()
        without.fit(series)
        base_preds = without.predict(festival_day - timedelta(days=20), 1)

        self.assertGreater(preds[0]['units'], base_preds[0]['units'])
        self.assertEqual(preds[0]['festival'], 'dashain')

    def test_festival_term_damps_just_after(self):
        series = {date(2025, 1, 1) + timedelta(days=i): 10 for i in range(200)}
        festival_day = date(2025, 7, 1)
        forecaster = SeasonalForecaster(festival_dates=[('dashain', festival_day)])
        forecaster.fit(series)

        day_after = forecaster.predict(festival_day + timedelta(days=1), 1)
        far_away = forecaster.predict(date(2025, 9, 1), 1)

        self.assertLess(day_after[0]['units'], far_away[0]['units'])

    def test_factors_are_clamped(self):
        """One absurd outlier week must not produce an absurd factor."""
        start = date(2025, 1, 1)
        series = {start + timedelta(days=i): 5 for i in range(100)}
        # Inject a wild spike on a Saturday.
        for i in range(100):
            day = start + timedelta(days=i)
            if day.weekday() == 5:
                series[day] = 5000

        forecaster = SeasonalForecaster().fit(series)
        self.assertLessEqual(max(forecaster.weekday_factors.values()), 1.65)

    def test_predictions_are_non_negative(self):
        start = date(2025, 1, 1)
        series = {start + timedelta(days=i): max(0, 20 - i) for i in range(25)}
        forecaster = SeasonalForecaster().fit(series)
        preds = forecaster.predict(date(2026, 1, 1), 60)
        self.assertTrue(all(p['units'] >= 0 for p in preds))

    def test_predict_respects_horizon(self):
        series = {date(2025, 1, 1) + timedelta(days=i): 10 for i in range(60)}
        forecaster = SeasonalForecaster().fit(series)
        for horizon in (1, 7, 30, 90):
            self.assertEqual(len(forecaster.predict(date(2026, 1, 1), horizon)), horizon)

    def test_empty_series_is_handled(self):
        forecaster = SeasonalForecaster().fit({})
        self.assertTrue(forecaster.fitted)
        preds = forecaster.predict(date(2026, 1, 1), 3)
        self.assertEqual(len(preds), 3)
        self.assertTrue(all(p['units'] == 0 for p in preds))

    def test_predict_before_fit_raises(self):
        with self.assertRaises(RuntimeError):
            SeasonalForecaster().predict(date(2026, 1, 1), 5)

    def test_components_are_exposed(self):
        series = {date(2025, 1, 1) + timedelta(days=i): 10 for i in range(90)}
        components = SeasonalForecaster().fit(series).components()
        self.assertIn('level', components)
        self.assertIn('weekday_factors', components)
        self.assertEqual(len(components['weekday_factors']), 7)


class SyntheticDataGenerationTests(TestCase):
    """The synthetic dataset must be reproducible and honestly labelled."""

    class _P:
        def __init__(self, id, category_id, popularity):
            self.id = id
            self.category_id = category_id
            self.popularity_score = popularity

    def _products(self):
        return [self._P(1, 10, 50), self._P(2, 10, 90)]

    def test_generation_is_deterministic(self):
        cats = {10: 'Dhana'}
        a = build_synthetic_history(self._products(), cats, rng=random.Random(99))
        b = build_synthetic_history(self._products(), cats, rng=random.Random(99))
        self.assertEqual(
            [s.daily for s in a], [s.daily for s in b],
            'Same seed must produce identical data',
        )

    def test_different_seeds_differ(self):
        cats = {10: 'Dhana'}
        a = build_synthetic_history(self._products(), cats, rng=random.Random(1))
        b = build_synthetic_history(self._products(), cats, rng=random.Random(2))
        self.assertNotEqual([s.daily for s in a], [s.daily for s in b])

    def test_generated_series_has_expected_length(self):
        series = build_synthetic_history(self._products(), {10: 'x'})
        for entry in series:
            self.assertEqual(len(entry.daily), 400)

    def test_units_are_non_negative_integers(self):
        series = build_synthetic_history(self._products(), {10: 'x'})
        for entry in series:
            for units in entry.daily.values():
                self.assertIsInstance(units, int)
                self.assertGreaterEqual(units, 0)


class DemandForecastApiTests(TestCase):
    """Authorization and provenance contract of the forecast endpoint.

    Authentication is JWT (``rest_framework_simplejwt``), not Django sessions, so
    these tests authenticate the same way the real clients do — via a bearer
    token — rather than using ``force_login``.
    """

    def setUp(self):
        from decimal import Decimal
        from rest_framework_simplejwt.tokens import RefreshToken
        from products.models import Category, Product

        self.admin = User.objects.create_user(
            'admin_u', password='pw123456', is_staff=True,
        )
        self.customer = User.objects.create_user('cust_u', password='pw123456')

        self.admin_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.admin).access_token}'
        }
        self.customer_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.customer).access_token}'
        }

        category = Category.objects.create(name='Dhoop & Agarbatti')
        self.product = Product.objects.create(
            name='Dhoop Batti', description='x', price=Decimal('120'),
            stock=10, category=category, popularity_score=80,
        )

    def _seed_history(self, products, days=120, units=5):
        today = timezone.now().date()
        for product in products:
            SyntheticSalesRecord.objects.bulk_create([
                SyntheticSalesRecord(
                    product=product, date=today - timedelta(days=days - 1 - i),
                    units_sold=units, is_synthetic=True,
                )
                for i in range(days)
            ])

    def test_requires_admin(self):
        """A logged-in customer must not reach the forecast (authorization intact)."""
        response = self.client.get(
            '/api/analytics/demand-forecast/', **self.customer_auth,
        )
        self.assertEqual(response.status_code, 403)

    def test_anonymous_is_rejected(self):
        response = self.client.get('/api/analytics/demand-forecast/')
        self.assertIn(response.status_code, (401, 403))

    def test_admin_is_allowed(self):
        response = self.client.get(
            '/api/analytics/demand-forecast/', **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200)

    def test_returns_empty_payload_when_no_history(self):
        response = self.client.get(
            '/api/analytics/demand-forecast/', **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['data_source'], 'none')
        self.assertFalse(data['is_synthetic'])
        self.assertEqual(data['forecasts'], [])

    def test_flags_synthetic_provenance(self):
        """The response must never let a caller mistake synthetic for real."""
        self._seed_history([self.product])

        response = self.client.get(
            '/api/analytics/demand-forecast/?horizon=7', **self.admin_auth,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data['data_source'], 'synthetic')
        self.assertTrue(data['is_synthetic'])
        self.assertIn('SYNTHETIC', data['provenance_note'])
        self.assertEqual(len(data['forecasts']), 1)
        self.assertTrue(data['forecasts'][0]['product']['name'])

    def test_horizon_is_clamped(self):
        self._seed_history([self.product])
        over = self.client.get(
            '/api/analytics/demand-forecast/?horizon=500', **self.admin_auth,
        ).json()
        under = self.client.get(
            '/api/analytics/demand-forecast/?horizon=0', **self.admin_auth,
        ).json()

        self.assertEqual(len(over['forecasts'][0]['predictions']), 90)
        self.assertEqual(len(under['forecasts'][0]['predictions']), 1)

    def test_invalid_product_filter_is_rejected(self):
        self._seed_history([self.product])
        response = self.client.get(
            '/api/analytics/demand-forecast/?product=abc', **self.admin_auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_product_filter_restricts_results(self):
        from decimal import Decimal
        from products.models import Category, Product
        second = Product.objects.create(
            name='Second', description='x', price=Decimal('10'),
            stock=5, category=Category.objects.first(), popularity_score=10,
        )
        self._seed_history([self.product, second])

        data = self.client.get(
            f'/api/analytics/demand-forecast/?product={self.product.id}',
            **self.admin_auth,
        ).json()
        self.assertEqual(len(data['forecasts']), 1)
        self.assertEqual(data['forecasts'][0]['product']['id'], self.product.id)

    def test_predictions_have_required_fields(self):
        self._seed_history([self.product])
        forecast = self.client.get(
            '/api/analytics/demand-forecast/?horizon=10', **self.admin_auth,
        ).json()['forecasts'][0]

        for key in ('forecast_total_units', 'avg_daily_units', 'stock_cover_days',
                    'restock_needed', 'projected_shortfall', 'metrics',
                    'components', 'predictions'):
            self.assertIn(key, forecast)

        self.assertEqual(len(forecast['predictions']), 10)
        for point in forecast['predictions']:
            self.assertIn('date', point)
            self.assertIn('units', point)
            self.assertGreaterEqual(point['units'], 0)

    def test_restock_flag_when_forecast_exceeds_stock(self):
        """High synthetic demand vs low stock must flag a restock need."""
        self._seed_history([self.product], units=40)
        forecast = self.client.get(
            '/api/analytics/demand-forecast/?horizon=30', **self.admin_auth,
        ).json()['forecasts'][0]

        self.assertTrue(forecast['restock_needed'])
        self.assertGreater(forecast['projected_shortfall'], 0)

    def test_aggregate_reports_mean_mape(self):
        self._seed_history([self.product])
        aggregate = self.client.get(
            '/api/analytics/demand-forecast/', **self.admin_auth,
        ).json()['aggregate']

        self.assertEqual(aggregate['products_covered'], 1)
        self.assertIsNotNone(aggregate['mean_mape'])
        self.assertIn('mean_mape_note', aggregate)

    def test_prediction_alerts_flag_synthetic_source(self):
        self._seed_history([self.product], units=20)
        data = self.client.get(
            '/api/analytics/predictions/', **self.admin_auth,
        ).json()

        self.assertTrue(data['forecast_available'])
        self.assertEqual(data['data_source'], 'synthetic')
        forecast_alerts = [a for a in data['alerts'] if a['type'] == 'forecast_restock']
        self.assertTrue(forecast_alerts, 'Expected a forecast-driven restock alert')
        self.assertEqual(forecast_alerts[0]['data_source'], 'synthetic')

    def test_prediction_alerts_unauthorized_for_customer(self):
        response = self.client.get('/api/analytics/predictions/', **self.customer_auth)
        self.assertEqual(response.status_code, 403)


class AreaBreakdownTests(TestCase):
    """`/api/analytics/areas/` — orders grouped by delivery area.

    The invariant that matters most here is arithmetic: the per-area revenues must
    add up to the headline `total_revenue` on `/api/analytics/sales/`. Two dashboard
    panels that disagree make both numbers worthless, so that is asserted directly
    rather than assumed.
    """

    def setUp(self):
        from decimal import Decimal
        from rest_framework_simplejwt.tokens import RefreshToken
        from accounts.models import UserProfile
        from products.models import Area, Category, Product, Vendor
        from orders.models import Order, OrderItem

        self.Decimal = Decimal
        self.Area = Area
        self.Product = Product
        self.Order = Order
        self.OrderItem = OrderItem

        self.manager = User.objects.create_user('area_mgr', password='pw12345678')
        UserProfile.objects.create(user=self.manager, role='admin')

        self.vendor_user = User.objects.create_user('area_vendor', password='pw12345678')
        UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.vendor = Vendor.objects.create(user=self.vendor_user, shop_name='Area Shop')

        self.customer = User.objects.create_user('area_cust', password='pw12345678')
        UserProfile.objects.create(user=self.customer, role='customer')

        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.manager).access_token}'
        }
        self.vendor_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.vendor_user).access_token}'
        }
        self.customer_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.customer).access_token}'
        }

        self.category = Category.objects.create(name='Area Cat')
        self.mine = Product.objects.create(
            name='Vendor Diyo', description='x', price=Decimal('100'),
            stock=50, category=self.category, vendor=self.vendor,
        )
        self.other = Product.objects.create(
            name='Other Sindoor', description='x', price=Decimal('50'),
            stock=50, category=self.category,
        )

        # The three seeded slugs, matching `core.constants.CITY_CHOICES`. Created
        # here rather than assumed, so the test does not depend on a migration.
        for slug, name in (('kathmandu', 'Kathmandu'), ('lalitpur', 'Lalitpur'),
                           ('bhaktapur', 'Bhaktapur')):
            Area.objects.get_or_create(slug=slug, defaults={'name': name})

    def _order(self, city, amount, product=None, status='pending'):
        order = self.Order.objects.create(
            user=self.customer, total_amount=self.Decimal(amount),
            delivery_fee=self.Decimal('100'), status=status,
            shipping_address='x', shipping_city=city, phone='9800000000',
        )
        OrderItem = self.OrderItem
        OrderItem.objects.create(
            order=order, product=product or self.other,
            product_name=(product or self.other).name, quantity=1,
            price=self.Decimal(amount),
        )
        return order

    def _add_item(self, order, product, price='10'):
        """Put a second product on an existing order."""
        return self.OrderItem.objects.create(
            order=order, product=product, product_name=product.name,
            quantity=1, price=self.Decimal(price),
        )

    def url(self):
        return '/api/analytics/areas/'

    # --- authorization -----------------------------------------------------

    def test_requires_a_staff_role(self):
        self.assertEqual(self.client.get(self.url()).status_code, 401)
        self.assertEqual(
            self.client.get(self.url(), **self.customer_auth).status_code, 403,
        )

    def test_a_manager_is_allowed(self):
        self.assertEqual(
            self.client.get(self.url(), **self.auth).status_code, 200,
        )

    def test_a_vendor_is_allowed_and_reports_vendor_scope(self):
        data = self.client.get(self.url(), **self.vendor_auth).json()
        self.assertEqual(data['scope'], 'vendor')

    # --- the arithmetic invariant ------------------------------------------

    def test_area_revenue_sums_to_the_sales_overview_total(self):
        """The two panels must not disagree, or neither number can be trusted."""
        self._order('kathmandu', '500')
        self._order('lalitpur', '300')
        self._order('bhaktapur', '200')

        areas = self.client.get(self.url(), **self.auth).json()
        sales = self.client.get('/api/analytics/sales/', **self.auth).json()

        self.assertEqual(areas['totals']['revenue'], sales['total_revenue'])
        self.assertEqual(areas['totals']['orders'], sales['total_orders'])
        self.assertAlmostEqual(
            sum(a['revenue'] for a in areas['areas']), sales['total_revenue'], places=2,
        )

    def test_share_percent_sums_to_one_hundred(self):
        self._order('kathmandu', '500')
        self._order('lalitpur', '300')
        self._order('bhaktapur', '200')

        areas = self.client.get(self.url(), **self.auth).json()['areas']
        self.assertAlmostEqual(sum(a['share_percent'] for a in areas), 100.0, places=1)

    # --- shape and content -------------------------------------------------

    def test_an_area_name_is_resolved_from_the_area_table(self):
        """`shipping_city` stores the slug; the panel must show "Lalitpur"."""
        self._order('lalitpur', '300')
        areas = self.client.get(self.url(), **self.auth).json()['areas']
        lalitpur = next(a for a in areas if a['slug'] == 'lalitpur')
        self.assertEqual(lalitpur['name'], 'Lalitpur')
        self.assertTrue(lalitpur['is_configured'])

    def test_configured_areas_with_no_orders_are_listed_at_zero(self):
        """Which areas have never been ordered from is the actionable half."""
        self._order('kathmandu', '500')
        areas = self.client.get(self.url(), **self.auth).json()['areas']
        by_slug = {a['slug']: a for a in areas}

        self.assertIn('lalitpur', by_slug)
        self.assertIn('bhaktapur', by_slug)
        self.assertEqual(by_slug['lalitpur']['orders'], 0)
        self.assertEqual(by_slug['lalitpur']['revenue'], 0.0)
        self.assertTrue(by_slug['lalitpur']['is_configured'])

    def test_an_order_for_an_unknown_area_is_not_dropped(self):
        """A city with no matching Area row must still appear, or totals break.

        This is the case an area rename or deletion produces, and silently dropping
        the order would make the rows stop summing to the headline figure.
        """
        self._order('kathmandu', '500')
        self._order('pokhara', '400')

        data = self.client.get(self.url(), **self.auth).json()
        by_slug = {a['slug']: a for a in data['areas']}

        self.assertIn('pokhara', by_slug)
        self.assertEqual(by_slug['pokhara']['revenue'], 400.0)
        self.assertFalse(by_slug['pokhara']['is_configured'])
        self.assertEqual(data['totals']['revenue'], 900.0)

    def test_cancelled_orders_are_counted_but_flagged_separately(self):
        """Revenue includes them (matching /sales/), and the count is exposed."""
        self._order('kathmandu', '500')
        self._order('kathmandu', '250', status='cancelled')

        data = self.client.get(self.url(), **self.auth).json()
        kathmandu = next(a for a in data['areas'] if a['slug'] == 'kathmandu')

        self.assertEqual(kathmandu['orders'], 2)
        self.assertEqual(kathmandu['cancelled_orders'], 1)
        self.assertEqual(kathmandu['revenue'], 750.0)
        self.assertEqual(data['totals']['cancelled'], 1)

    def test_rows_are_ordered_by_revenue_descending(self):
        self._order('bhaktapur', '100')
        self._order('kathmandu', '900')
        self._order('lalitpur', '400')

        areas = self.client.get(self.url(), **self.auth).json()['areas']
        revenues = [a['revenue'] for a in areas]
        self.assertEqual(revenues, sorted(revenues, reverse=True))
        self.assertEqual(areas[0]['slug'], 'kathmandu')

    def test_an_empty_database_reports_zero_rather_than_dividing_by_zero(self):
        data = self.client.get(self.url(), **self.auth).json()
        self.assertEqual(data['totals']['revenue'], 0.0)
        self.assertEqual(data['totals']['orders'], 0)
        # The three configured areas are still listed, all at 0.0% share.
        self.assertTrue(data['areas'])
        self.assertTrue(all(a['share_percent'] == 0.0 for a in data['areas']))

    # --- scoping -----------------------------------------------------------

    def test_a_vendor_sees_only_areas_its_own_products_shipped_to(self):
        """Vendor scoping must hold here too, not just on /sales/."""
        self._order('kathmandu', '500', product=self.mine)
        self._order('lalitpur', '900', product=self.other)

        data = self.client.get(self.url(), **self.vendor_auth).json()
        by_slug = {a['slug']: a for a in data['areas']}

        self.assertEqual(data['totals']['revenue'], 500.0)
        self.assertEqual(by_slug['kathmandu']['revenue'], 500.0)
        self.assertEqual(by_slug['lalitpur']['revenue'], 0.0)

    def test_a_manager_sees_the_whole_catalogue(self):
        self._order('kathmandu', '500', product=self.mine)
        self._order('lalitpur', '900', product=self.other)

        data = self.client.get(self.url(), **self.auth).json()
        self.assertEqual(data['totals']['revenue'], 1400.0)
        self.assertEqual(data['scope'], 'all')


class VendorOrderScopingTests(TestCase):
    """A vendor's revenue must not be multiplied by how many of their products an
    order happens to contain.

    This is a real bug that was found by comparing two panels rather than by reading
    code. The scope was `filter(items__product__vendor=vendor).distinct()` — a JOIN —
    so an order holding two of the vendor's products produced two rows. A flat
    `aggregate()` happened to be correct, which is what hid it; the first *grouped*
    aggregate over the same scope reported **2780** where the truth was 1810.

    `.distinct()` does not rescue it: Django applies DISTINCT to the grouped rows, so
    the duplication survives into the aggregate. `Exists` produces no join, so both
    shapes are correct.
    """

    def setUp(self):
        from decimal import Decimal
        from rest_framework_simplejwt.tokens import RefreshToken
        from accounts.models import UserProfile
        from products.models import Area, Category, Product, Vendor
        from orders.models import Order, OrderItem

        self.Decimal = Decimal

        self.manager = User.objects.create_user('scope_mgr', password='pw12345678')
        UserProfile.objects.create(user=self.manager, role='admin')

        self.vendor_user = User.objects.create_user('scope_vendor', password='pw12345678')
        UserProfile.objects.create(user=self.vendor_user, role='vendor')
        vendor = Vendor.objects.create(user=self.vendor_user, shop_name='Scope Shop')

        self.customer = User.objects.create_user('scope_cust', password='pw12345678')
        UserProfile.objects.create(user=self.customer, role='customer')

        self.auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.manager).access_token}'
        }
        self.vendor_auth = {
            'HTTP_AUTHORIZATION': f'Bearer {RefreshToken.for_user(self.vendor_user).access_token}'
        }

        category = Category.objects.create(name='Scope Cat')
        self.mine = Product.objects.create(
            name='Scope Diyo', description='x', price=Decimal('100'),
            stock=50, category=category, vendor=vendor,
        )
        self.mine2 = Product.objects.create(
            name='Scope Batti', description='x', price=Decimal('50'),
            stock=50, category=category, vendor=vendor,
        )
        self.foreign = Product.objects.create(
            name='Foreign Sindoor', description='x', price=Decimal('30'),
            stock=50, category=category,
        )

        Area.objects.get_or_create(slug='kathmandu', defaults={'name': 'Kathmandu'})

        # One order containing TWO of the vendor's products — the shape that exposed
        # the bug — and one containing only a foreign product.
        self.shared = Order.objects.create(
            user=self.customer, total_amount=Decimal('500'), delivery_fee=Decimal('100'),
            shipping_address='x', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(order=self.shared, product=self.mine,
                                 product_name=self.mine.name, quantity=1, price=Decimal('400'))
        OrderItem.objects.create(order=self.shared, product=self.mine2,
                                 product_name=self.mine2.name, quantity=1, price=Decimal('100'))

        self.foreign_order = Order.objects.create(
            user=self.customer, total_amount=Decimal('900'), delivery_fee=Decimal('100'),
            shipping_address='x', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(order=self.foreign_order, product=self.foreign,
                                 product_name=self.foreign.name, quantity=1, price=Decimal('900'))

    def test_a_vendor_order_with_two_of_their_items_counts_once(self):
        data = self.client.get('/api/analytics/areas/', **self.vendor_auth).json()
        kathmandu = next(a for a in data['areas'] if a['slug'] == 'kathmandu')

        self.assertEqual(kathmandu['orders'], 1,
                         'the order was counted once per matching item')
        self.assertEqual(kathmandu['revenue'], 500.0,
                         'the order total was multiplied by its matching item count')
        self.assertEqual(data['totals']['revenue'], 500.0)
        self.assertEqual(data['totals']['orders'], 1)

    def test_the_sales_overview_agrees_with_the_area_breakdown(self):
        areas = self.client.get('/api/analytics/areas/', **self.vendor_auth).json()
        sales = self.client.get('/api/analytics/sales/', **self.vendor_auth).json()

        self.assertEqual(areas['totals']['revenue'], sales['total_revenue'])
        self.assertEqual(areas['totals']['orders'], sales['total_orders'])
        self.assertEqual(sales['total_revenue'], 500.0)

    def test_another_vendors_order_is_excluded_entirely(self):
        data = self.client.get('/api/analytics/areas/', **self.vendor_auth).json()
        self.assertEqual(data['totals']['revenue'], 500.0,
                         'an order with none of this vendor\'s products was included')

    def test_a_manager_still_sees_every_order_once(self):
        data = self.client.get('/api/analytics/areas/', **self.auth).json()
        self.assertEqual(data['totals']['revenue'], 1400.0)
        self.assertEqual(data['totals']['orders'], 2)


class InventoryAnalyticsTests(TestCase):
    """`/analytics/inventory/` was the one analytics endpoint with **no coverage of
    any kind** — no unit test, no live assertion, and no client calling it.

    It is easy to look at it and conclude it is covered, because the dashboard's
    `/products` page also shows a stock column and the home page has "Out of Stock"
    and "Low Stock" tiles. Those read from different places: the tiles come from
    `/analytics/sales/` (`total_products`) and `/products/`' own per-row rendering.
    Nothing has ever exercised `InventoryView`.

    The tests deliberately set stock explicitly rather than leaning on the seeded
    catalogue. The seeded minimum is **25** units and the endpoints' threshold is
    **10**, so on demo data every count is legitimately zero — which means a test
    written against seed data would pass no matter what the thresholds did.
    """

    URL = '/api/analytics/inventory/'

    def setUp(self):
        from decimal import Decimal
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken
        from accounts.models import UserProfile
        from products.models import Category, Product, Vendor

        self.Decimal = Decimal

        self.manager = User.objects.create_user('inv_mgr', password='pw12345678')
        UserProfile.objects.create(user=self.manager, role='admin')

        self.vendor_user = User.objects.create_user('inv_vendor', password='pw12345678')
        UserProfile.objects.create(user=self.vendor_user, role='vendor')
        self.shop = Vendor.objects.create(user=self.vendor_user, shop_name='Inv Shop')

        self.customer = User.objects.create_user('inv_cust', password='pw12345678')
        UserProfile.objects.create(user=self.customer, role='customer')

        self.mgr_client = APIClient()
        self.mgr_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.manager).access_token}')
        self.vendor_client = APIClient()
        self.vendor_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.vendor_user).access_token}')
        self.customer_client = APIClient()
        self.customer_client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.customer).access_token}')

        category = Category.objects.create(name='Inv Cat')

        def product(name, stock, vendor=None, active=True):
            return Product.objects.create(
                name=name, description='x', price=Decimal('100'),
                stock=stock, category=category, vendor=vendor, is_active=active,
            )

        # Stock chosen so every branch is exercised by an explicit number.
        self.ok = product('Inv Healthy', 500, self.shop)          # plenty
        self.low = product('Inv Low', 4, self.shop)               # 0 < stock < 10
        self.out = product('Inv Out', 0, self.shop)               # stock == 0
        self.at_threshold = product('Inv Exactly Ten', 10, self.shop)  # NOT low: < 10
        self.foreign_low = product('Inv Foreign Low', 3)          # someone else's
        self.inactive_low = product('Inv Inactive Low', 2, self.shop, active=False)

    def test_a_customer_is_refused(self):
        self.assertEqual(self.customer_client.get(self.URL).status_code, 403)

    def test_totals_count_only_active_products(self):
        data = self.mgr_client.get(self.URL).json()
        # Six products exist, but one is inactive so it is not part of the report.
        self.assertEqual(data['total_products'], 5)

    def test_low_stock_uses_a_strict_threshold(self):
        """`stock__lt=10`. A product sitting exactly on 10 is not low, and a test
        written as `<= 10` would agree with the code only by luck.

        **The two lists are nested, not disjoint.** `stock__lt=10` includes `stock=0`,
        so every out-of-stock product also appears in `low_stock_products`. That is
        not a bug, but it is a trap for a screen that renders both lists: the
        out-of-stock items would be shown twice. Pinned here because the first version
        of this test got it wrong, and the assertion caught it.
        """
        data = self.mgr_client.get(self.URL).json()
        # Low(4) + Out(0) + Foreign Low(3) = 3. Exactly-Ten is NOT low; the inactive
        # product is excluded from the report entirely.
        self.assertEqual(data['low_stock_count'], 3)
        names = {p['name'] for p in data['low_stock_products']}
        self.assertIn('Inv Low', names)
        self.assertIn('Inv Out', names, 'an out-of-stock product is also below 10')
        self.assertNotIn('Inv Exactly Ten', names,
                         'a product on exactly the threshold was treated as low')
        self.assertNotIn('Inv Inactive Low', names,
                         'an inactive product was reported in a live stock list')

    def test_out_of_stock_is_a_subset_of_low_stock(self):
        """The relationship a UI must know about, stated as its own assertion."""
        data = self.mgr_client.get(self.URL).json()
        low_names = {p['name'] for p in data['low_stock_products']}
        out_names = {
            p.name for p in self._active_products().filter(stock=0)
        }
        self.assertTrue(out_names.issubset(low_names),
                        f'{out_names - low_names} is out of stock but not low')

    def _active_products(self):
        from products.models import Product
        return Product.objects.filter(is_active=True)

    def test_out_of_stock_is_zero_stock_only(self):
        data = self.mgr_client.get(self.URL).json()
        self.assertEqual(data['out_of_stock_count'], 1)

    def test_a_low_stock_row_carries_what_the_screen_needs(self):
        data = self.mgr_client.get(self.URL).json()
        row = next(p for p in data['low_stock_products'] if p['name'] == 'Inv Low')
        self.assertEqual(row['stock'], 4)
        self.assertEqual(row['category'], 'Inv Cat')
        self.assertIn('id', row)

    def test_total_stock_units_matches_the_reported_products(self):
        """The aggregate must describe the same set the counts do.

        A `total_stock_units` computed over a different queryset than
        `total_products` would be the sort of panel that disagrees with itself.
        """
        data = self.mgr_client.get(self.URL).json()
        expected = 500 + 4 + 0 + 10 + 3        # the five active products, inactive excluded
        self.assertEqual(data['total_stock_units'], expected)

    def test_a_vendor_sees_only_their_own_stock(self):
        data = self.vendor_client.get(self.URL).json()
        # Four of the vendor's products are active (the inactive one is excluded):
        # Healthy(500), Low(4), Out(0), Exactly Ten(10).
        self.assertEqual(data['total_products'], 4)
        # Low(4) + Out(0) = 2.
        self.assertEqual(data['low_stock_count'], 2)
        names = {p['name'] for p in data['low_stock_products']}
        self.assertEqual(names, {'Inv Low', 'Inv Out'})
        self.assertNotIn('Inv Foreign Low', names,
                         "a vendor was shown another shop's low stock")

    def test_the_low_stock_list_is_capped(self):
        """`low_stock[:20]`. A vendor with more than 20 low items must get 20 rows,
        not the whole list — the cap is intentional and worth pinning so nobody
        'fixes' it into an unbounded payload."""
        from products.models import Category, Product
        category = Category.objects.first()
        for i in range(25):
            Product.objects.create(
                name=f'Inv Bulk {i:02d}', description='x', price=self.Decimal('10'),
                stock=1, category=category, vendor=self.shop,
            )
        data = self.vendor_client.get(self.URL).json()
        self.assertEqual(len(data['low_stock_products']), 20)
        # The count still reports the truth rather than the truncated length.
        self.assertGreater(data['low_stock_count'], 20)
