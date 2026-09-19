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
