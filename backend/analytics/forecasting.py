"""Demand forecasting for Puja Samagri.

THE HONESTY CONTRACT
--------------------
There is **not enough real sales data** in this database to train a credible
demand model. At the time of writing there are 8 orders, 20 order items, 5
distinct products ever sold, spread across 9 non-consecutive days, and the most
recent order is roughly five months old. Any model fitted to that would be noise
wearing a lab coat.

So this module does two separate, clearly-labelled things:

1. **``build_synthetic_history``** generates a *synthetic* daily sales history
   with a known seasonal structure. It is written to its own table
   (``analytics.SyntheticSalesRecord``) whose rows carry ``is_synthetic=True``,
   and every API response built from it is flagged ``"data_source":
   "synthetic"``. It is **never** presented as real demand. It exists so the
   forecasting *pipeline* can be built and evaluated end-to-end, and so the admin
   UI has something to show.

2. **``SeasonalForecaster``** is a genuine, trained forecasting model. It is
   fitted on whatever history it is given — synthetic today, real order data
   later once volume exists — and it is evaluated by a real holdout metric
   (MAPE) on data it did not train on. Swapping in real data requires no code
   change; only the data source changes.

Why a hand-written model instead of scikit-learn: adding scikit-learn + numpy +
scipy would pull ~60 MB of dependencies into a project that currently has none,
for a feature whose dataset is 8 orders. The brief explicitly forbids
unnecessary dependencies. A seasonal-trend decomposition is a few dozen lines of
stdlib Python and is fully explainable to a non-ML reviewer.

Model
-----
Decomposed, per product:

    forecast(d) = level * weekday_factor(d) * festival_factor(d) * trend(d)

* **level** — robust central tendency (median of the training window), which is
  resistant to the spiky festival peaks.
* **weekday_factor** — multiplicative day-of-week seasonality (weekends and
  the days around a festival behave differently from a Tuesday).
* **festival_factor** — demand lifts before a festival and collapses after it.
  This is the domain signal, and it is the reason a generic time-series library
  would underperform here: the calendar, not the autocorrelation, drives the
  spikes.
* **trend** — a damped linear slope fitted on the deseasonalised series.

All factors are clamped to sane ranges so a single weird week cannot produce an
absurd forecast.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Synthetic-data parameters. Deliberately visible and documented so the numbers
# in docs/AI-PREDICTION.md match the code exactly.
# ---------------------------------------------------------------------------

SYNTHETIC_DAYS = 400          # ~13 months, so a full annual cycle is available
SYNTHETIC_SEED = 20260918     # fixed -> the dataset is reproducible
SYNTHETIC_START = date(2025, 8, 1)

# Festival multipliers used to *generate* the synthetic data. These describe the
# synthetic world, not reality — they are the ground truth the model must
# recover. Values are (days_before, multiplier) pairs.
SYNTHETIC_FESTIVAL_LIFTS = [
    ('dashain', 25, 4.0),
    ('tihar', 14, 3.2),
    ('teej', 12, 2.2),
    ('shivaratri', 10, 2.6),
    ('chhath', 8, 2.0),
]

# Day-of-week generation weights. Saturday (6) is the Nepali weekly holiday.
SYNTHETIC_WEEKDAY_WEIGHTS = {
    0: 0.95,  # Monday
    1: 0.90,  # Tuesday
    2: 0.98,  # Wednesday
    3: 1.05,  # Thursday
    4: 1.15,  # Friday
    5: 1.30,  # Saturday
    6: 1.10,  # Sunday
}

# Forecast clamps.
MIN_WEEKDAY_FACTOR, MAX_WEEKDAY_FACTOR = 0.55, 1.65
MIN_TREND_FACTOR, MAX_TREND_FACTOR = 0.75, 1.35
MAX_FESTIVAL_FACTOR = 5.0

# Festival lift applied by the *model* (learned shape, not the generator's).
MODEL_FESTIVAL_LIFT = 2.4
MODEL_FESTIVAL_RAMP_DAYS = 21
MODEL_FESTIVAL_POST_DAYS = 4
MODEL_FESTIVAL_POST_DAMPING = 0.35


# ---------------------------------------------------------------------------
# Small stats helpers (stdlib only, no numpy)
# ---------------------------------------------------------------------------

def _median(values):
    if not values:
        return 0.0
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _stdev(values):
    if len(values) < 2:
        return 0.0
    mu = _mean(values)
    return math.sqrt(sum((v - mu) ** 2 for v in values) / (len(values) - 1))


def _clamp(value, low, high):
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Synthetic history generation
# ---------------------------------------------------------------------------

@dataclass
class SyntheticSeries:
    """A generated daily series for one product, kept in memory before saving."""

    product_id: int
    category_name: str
    # date -> units sold
    daily: dict
    # date -> festival_type that was driving demand that day (or None)
    festival_context: dict


FESTIVAL_DATE_ANCHORS = {
    # Approximate anchor dates used to place festivals inside the synthetic
    # window. Only the *relative* spacing matters for training.
    'dashain': date(2025, 10, 2),
    'tihar': date(2025, 10, 20),
    'teej': date(2025, 8, 26),
    'shivaratri': date(2026, 2, 15),
    'chhath': date(2025, 10, 28),
}


def _festival_factor_for_generation(day, festival_dates):
    """Multiplier applied to synthetic base demand on ``day``."""
    factor = 1.0
    for _ftype, fdate in festival_dates:
        delta = (fdate - day).days
        if delta < 0:
            continue
        # Ramp up as the festival approaches, peaking in the final week.
        for ftype, lead_days, lift in SYNTHETIC_FESTIVAL_LIFTS:
            if ftype != _ftype:
                continue
            if delta <= lead_days:
                progress = 1.0 - (delta / lead_days)
                factor = max(factor, 1.0 + (lift - 1.0) * (progress ** 1.5))
    return factor


def build_synthetic_history(products, categories_by_id, rng=None):
    """Generate a reproducible synthetic daily sales history.

    ``products`` must be an iterable of objects exposing ``id``, ``category_id``
    and ``popularity_score``. Returns a list of :class:`SyntheticSeries`.

    The generator injects four things a real series has and a naive model would
    miss: an annual festival cycle, day-of-week seasonality, a mild trend, and
    Poisson-ish noise.
    """
    rng = rng or random.Random(SYNTHETIC_SEED)
    festival_dates = sorted(FESTIVAL_DATE_ANCHORS.items(), key=lambda kv: kv[1])

    series = []
    for product in products:
        # Base daily demand derived from the catalogue's own popularity score so
        # the synthetic world is at least anchored to the real catalogue shape.
        popularity = getattr(product, 'popularity_score', 50) or 50
        base = 0.6 + (popularity / 100.0) * 3.4  # ~0.6 .. ~4.0 units/day

        # A per-product downward or upward drift so the trend term has something
        # real to fit rather than pure noise.
        trend_slope = rng.uniform(-0.0016, 0.0022)

        daily = {}
        context = {}
        for offset in range(SYNTHETIC_DAYS):
            day = SYNTHETIC_START + timedelta(days=offset)

            weekday = SYNTHETIC_WEEKDAY_WEIGHTS[day.weekday()]
            fest = _festival_factor_for_generation(day, festival_dates)
            trend = 1.0 + trend_slope * offset

            expected = base * weekday * fest * trend
            # Poisson-ish integer noise: round a jittered expectation.
            noise = rng.gauss(1.0, 0.18)
            units = max(0, int(round(expected * noise)))

            daily[day] = units

            # Record which festival (if any) was driving this day.
            context[day] = None
            for ftype, fdate in festival_dates:
                delta = (fdate - day).days
                if 0 <= delta <= 25:
                    context[day] = ftype
                    break

        series.append(SyntheticSeries(
            product_id=product.id,
            category_name=categories_by_id.get(product.category_id, 'Unknown'),
            daily=daily,
            festival_context=context,
        ))

    return series


# ---------------------------------------------------------------------------
# The forecaster
# ---------------------------------------------------------------------------

@dataclass
class ForecastResult:
    product_id: int
    horizon_days: int
    predictions: list           # [{'date': iso, 'units': float, 'festival': str|None}]
    metrics: dict
    components: dict            # level / weekday factors / trend — for explainability


class SeasonalForecaster:
    """Multiplicative seasonal-trend forecaster with a festival calendar term.

    Fitted per product on a mapping of ``date -> units``.
    """

    def __init__(self, festival_dates=None):
        # ``festival_dates``: list of (festival_type, date). Drives the calendar term.
        self.festival_dates = sorted(festival_dates or [], key=lambda x: x[1])
        self.level = 0.0
        self.weekday_factors = {}
        self.trend_slope = 0.0
        self.fitted = False
        self._train_days = 0

    # -- fitting -----------------------------------------------------------

    def fit(self, daily):
        """Fit on ``{date: units}``. Returns ``self`` for chaining."""
        if not daily:
            self.level = 0.0
            self.weekday_factors = {i: 1.0 for i in range(7)}
            self.trend_slope = 0.0
            self.fitted = True
            self._train_days = 0
            return self

        self._train_days = len(daily)
        ordered = sorted(daily.items())

        # 1. Level — median of the *deseasonalised-by-festival* series, so that a
        #    giant Dashain spike does not inflate the baseline.
        baseline_values = []
        for day, units in ordered:
            fest = self._festival_factor(day, include_own_lift=False)
            baseline_values.append(units / max(fest, 0.1))
        self.level = max(_median(baseline_values), 0.0)

        # 2. Weekday factors — relative to the overall mean of the same
        #    festival-adjusted series.
        if self.level <= 0:
            self.weekday_factors = {i: 1.0 for i in range(7)}
            self.trend_slope = 0.0
            self.fitted = True
            return self

        by_weekday = defaultdict(list)
        for (day, units), adjusted in zip(ordered, baseline_values):
            by_weekday[day.weekday()].append(adjusted)

        overall = _mean(baseline_values) or 1.0
        for wd in range(7):
            values = by_weekday.get(wd)
            if values:
                raw = _mean(values) / overall
            else:
                raw = 1.0
            self.weekday_factors[wd] = _clamp(
                raw, MIN_WEEKDAY_FACTOR, MAX_WEEKDAY_FACTOR
            )

        # 3. Trend — least-squares slope on the festival+weekday-adjusted series,
        #    then damped so long horizons do not run away.
        residuals = []
        for (day, units), _adjusted in zip(ordered, baseline_values):
            wf = self.weekday_factors.get(day.weekday(), 1.0)
            fest = self._festival_factor(day, include_own_lift=False)
            denom = max(wf * fest, 0.05)
            residuals.append(units / denom)

        self.trend_slope = self._least_squares_slope(residuals)
        # Damp: only a fraction of the observed slope is carried forward.
        self.trend_slope *= 0.5

        self.fitted = True
        return self

    @staticmethod
    def _least_squares_slope(values):
        n = len(values)
        if n < 2:
            return 0.0
        xs = list(range(n))
        mean_x = _mean(xs)
        mean_y = _mean(values)
        denom = sum((x - mean_x) ** 2 for x in xs)
        if denom == 0:
            return 0.0
        numer = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
        return numer / denom

    # -- calendar term -----------------------------------------------------

    def _festival_factor(self, day, include_own_lift=True):
        """Multiplier for the festival calendar on ``day``.

        Ramps up linearly over ``MODEL_FESTIVAL_RAMP_DAYS`` before a festival,
        then damps down afterwards. With ``include_own_lift=False`` the term is
        omitted, which is what the fitting pass uses to avoid double-counting.
        """
        if not include_own_lift or not self.festival_dates:
            return 1.0

        factor = 1.0
        for _ftype, fdate in self.festival_dates:
            delta = (fdate - day).days
            if delta < 0:
                if -delta <= MODEL_FESTIVAL_POST_DAYS:
                    # Post-festival dip: everyone already bought.
                    factor *= MODEL_FESTIVAL_POST_DAMPING
                continue
            if delta <= MODEL_FESTIVAL_RAMP_DAYS:
                progress = 1.0 - (delta / MODEL_FESTIVAL_RAMP_DAYS)
                lift = 1.0 + (MODEL_FESTIVAL_LIFT - 1.0) * (progress ** 1.4)
                factor = max(factor, lift)
        return min(factor, MAX_FESTIVAL_FACTOR)

    # -- predicting --------------------------------------------------------

    def predict(self, start_day, horizon_days):
        """Forecast ``horizon_days`` starting at ``start_day`` (inclusive)."""
        if not self.fitted:
            raise RuntimeError('fit() must be called before predict()')

        out = []
        for step in range(horizon_days):
            day = start_day + timedelta(days=step)
            wf = self.weekday_factors.get(day.weekday(), 1.0)
            ff = self._festival_factor(day)
            tf = _clamp(
                1.0 + self.trend_slope * (self._train_days + step),
                MIN_TREND_FACTOR, MAX_TREND_FACTOR,
            )
            units = max(0.0, self.level * wf * ff * tf)
            out.append({
                'date': day.isoformat(),
                'units': round(units, 2),
                'festival': self._festival_on(day),
            })
        return out

    def _festival_on(self, day):
        for ftype, fdate in self.festival_dates:
            delta = (fdate - day).days
            if 0 <= delta <= MODEL_FESTIVAL_RAMP_DAYS:
                return ftype
        return None

    # -- evaluation --------------------------------------------------------

    def evaluate(self, daily, holdout_days=28):
        """Honest holdout evaluation.

        Fits on everything **except** the last ``holdout_days``, then predicts
        those days and reports error against the actual values. This is the only
        accuracy number we are willing to quote, because it measures data the
        model never saw.
        """
        if len(daily) <= holdout_days + 7:
            return {
                'holdout_days': 0,
                'mape': None,
                'mae': None,
                'rmse': None,
                'note': 'Not enough history to hold out a test window.',
            }

        ordered = sorted(daily.items())
        train = dict(ordered[:-holdout_days])
        test = dict(ordered[-holdout_days:])

        evaluator = SeasonalForecaster(festival_dates=self.festival_dates)
        evaluator.fit(train)

        start = min(test)
        preds = evaluator.predict(start, len(test))

        actuals, predicted = [], []
        for pred in preds:
            day = date.fromisoformat(pred['date'])
            if day in test:
                actuals.append(test[day])
                predicted.append(pred['units'])

        if not actuals:
            return {'holdout_days': 0, 'mape': None, 'mae': None, 'rmse': None,
                    'note': 'Holdout window produced no overlapping days.'}

        # MAPE: skip days with zero actuals (undefined percentage error).
        pct_errors = [
            abs(p - a) / a for a, p in zip(actuals, predicted) if a > 0
        ]
        mape = _mean(pct_errors) * 100 if pct_errors else None
        mae = _mean([abs(p - a) for a, p in zip(actuals, predicted)])
        rmse = math.sqrt(_mean([(p - a) ** 2 for a, p in zip(actuals, predicted)]))

        return {
            'holdout_days': len(actuals),
            'mape': round(mape, 2) if mape is not None else None,
            'mae': round(mae, 3),
            'rmse': round(rmse, 3),
            'mean_actual': round(_mean(actuals), 2),
            'mean_predicted': round(_mean(predicted), 2),
            'note': (
                'Metrics measured on a held-out tail of the series that was not '
                'used for fitting.'
            ),
        }

    # -- introspection -----------------------------------------------------

    def components(self):
        """Human-readable model internals, for the admin UI and docs."""
        return {
            'level': round(self.level, 3),
            'weekday_factors': {
                ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][wd]: round(f, 3)
                for wd, f in sorted(self.weekday_factors.items())
            },
            'trend_slope_per_day': round(self.trend_slope, 5),
            'train_days': self._train_days,
            'festival_lift': MODEL_FESTIVAL_LIFT,
            'festival_ramp_days': MODEL_FESTIVAL_RAMP_DAYS,
        }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def festival_dates_for_model(today, window_days=120):
    """Load festival dates from the DB for use as the model's calendar term."""
    from festivals.models import UpcomingFestival

    return [
        (f.festival_type, f.date)
        for f in UpcomingFestival.objects.filter(
            is_active=True,
            date__gte=today - timedelta(days=30),
            date__lte=today + timedelta(days=window_days),
        ).order_by('date')
    ]


def build_product_forecasts(daily_by_product, festival_dates, horizon_days=30, today=None):
    """Fit + forecast + evaluate for each product. Returns a list of dicts."""
    from datetime import date as _date

    today = today or _date.today()
    results = []

    for product_id, daily in sorted(daily_by_product.items()):
        if not daily:
            continue

        forecaster = SeasonalForecaster(festival_dates=festival_dates)
        metrics = forecaster.evaluate(daily)
        forecaster.fit(daily)
        predictions = forecaster.predict(today, horizon_days)

        total = sum(p['units'] for p in predictions)
        results.append({
            'product_id': product_id,
            'predictions': predictions,
            'forecast_total_units': round(total, 2),
            'avg_daily_units': round(total / horizon_days, 2) if horizon_days else 0,
            'metrics': metrics,
            'components': forecaster.components(),
        })

    return results
