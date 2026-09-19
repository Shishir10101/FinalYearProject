"""Day 2 end-to-end verification.

Runs against a live backend on :8000. Covers the Day 1 guarantees (so we can
prove no regression) plus the Day 2 additions (recommendations, forecast,
festival calendar) and — critically — re-checks that authorization was NOT
weakened while adding the new admin endpoints.
"""

import json
import urllib.request
import urllib.error

BASE = 'http://127.0.0.1:8000/api'

passed = 0
failed = 0
failures = []


def call(method, path, token=None, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return 0, str(e)


def check(name, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print('  PASS  ' + name)
    else:
        failed += 1
        failures.append(name + (' :: ' + str(detail) if detail else ''))
        print('  FAIL  ' + name + (' :: ' + str(detail) if detail else ''))


def login(username, password):
    status, data = call('POST', '/auth/login/', body={'username': username, 'password': password})
    if status == 200 and isinstance(data, dict):
        return data.get('access')
    return None


print('=' * 62)
print('DAY 2 END-TO-END VERIFICATION')
print('=' * 62)

admin_token = login('admin', 'admin123')
customer_token = login('testuser', 'test1234')

check('admin login works', admin_token is not None)
check('customer login works', customer_token is not None)

# ---------------------------------------------------------------- Day 1 regression
print('\n--- Day 1 regressions (must still hold) ---')

status, data = call('GET', '/orders/config/')
check('GET /orders/config/ public', status == 200, status)
check('delivery_fee is a number', isinstance(data.get('delivery_fee'), (int, float)), data)
delivery_fee = data.get('delivery_fee')

status, products = call('GET', '/products/')
check('GET /products/ public', status == 200, status)
check('products list non-empty', bool(products))

status, featured = call('GET', '/products/featured/')
check('GET /products/featured/ public', status == 200, status)

status, cats = call('GET', '/products/categories/')
check('GET /products/categories/ public', status == 200, status)

status, _ = call('GET', '/orders/cart/')
check('cart requires auth (401)', status == 401, status)

status, _ = call('GET', '/orders/', token=customer_token)
check('customer can list own orders', status == 200, status)

# ---------------------------------------------------------------- festival calendar
print('\n--- Festival calendar repair ---')

status, upcoming = call('GET', '/festivals/upcoming/')
check('GET /festivals/upcoming/ public', status == 200, status)
check('upcoming festivals no longer empty', isinstance(upcoming, list) and len(upcoming) > 0,
      'got %s' % (len(upcoming) if isinstance(upcoming, list) else upcoming))

if isinstance(upcoming, list) and upcoming:
    check('festivals are in the future (all)',
          all(f['date'] >= '2026-09-18' for f in upcoming),
          [f['date'] for f in upcoming])

# ---------------------------------------------------------------- recommendations
print('\n--- Recommendation engine ---')

status, rec = call('GET', '/festivals/recommendations/')
check('GET /festivals/recommendations/ public', status == 200, status)
check('has meta block', isinstance(rec, dict) and 'meta' in rec)
check('algorithm is reported', rec['meta']['algorithm'] == 'weighted-signal-ranker', rec['meta'])
check('anonymous marked not personalised', rec['meta']['personalised'] is False)

recs = rec['recommended_products']
check('recommendations non-empty', len(recs) > 0, len(recs))
check('every recommendation has a score > 0',
      all(p['recommendation']['score'] > 0 for p in recs))
check('every recommendation has at least one reason',
      all(len(p['recommendation']['reasons']) > 0 for p in recs))
check('every reason has code + text + points',
      all(r.get('code') and r.get('text') and r.get('points', 0) > 0
          for p in recs for r in p['recommendation']['reasons']))
check('score equals sum of reason points (all products)',
      all(p['recommendation']['score'] == sum(r['points'] for r in p['recommendation']['reasons'])
          for p in recs))
check('no out-of-stock products recommended', all(p['in_stock'] for p in recs))

scores = [p['recommendation']['score'] for p in recs]
check('recommendations are sorted descending', scores == sorted(scores, reverse=True), scores[:6])

# The set()-based bug: order must be stable across identical requests.
order_a = [p['id'] for p in call('GET', '/festivals/recommendations/')[1]['recommended_products']]
order_b = [p['id'] for p in call('GET', '/festivals/recommendations/')[1]['recommended_products']]
check('ordering is deterministic across requests', order_a == order_b)

status, rec_p = call('GET', '/festivals/recommendations/?limit=3', token=customer_token)
check('personalised request succeeds', status == 200, status)
check('logged-in marked personalised', rec_p['meta']['personalised'] is True)
check('limit=3 respected', len(rec_p['recommended_products']) == 3, len(rec_p['recommended_products']))

status, rec_bad = call('GET', '/festivals/recommendations/?limit=abc')
check('invalid limit does not 500', status == 200, status)

# ---------------------------------------------------------------- demand forecast
print('\n--- Demand forecast ---')

status, _ = call('GET', '/analytics/demand-forecast/')
check('forecast requires auth (401/403)', status in (401, 403), status)

status, _ = call('GET', '/analytics/demand-forecast/', token=customer_token)
check('forecast forbidden for customer (403) -- authz NOT weakened', status == 403, status)

status, fc = call('GET', '/analytics/demand-forecast/?horizon=30&limit=5', token=admin_token)
check('forecast allowed for admin', status == 200, status)
check('data_source flagged synthetic', fc['data_source'] == 'synthetic', fc.get('data_source'))
check('is_synthetic is True', fc['is_synthetic'] is True)
check('provenance note present', 'SYNTHETIC' in fc.get('provenance_note', ''))
check('forecasts returned', len(fc['forecasts']) > 0, len(fc['forecasts']))
check('aggregate has mean_mape', fc['aggregate'].get('mean_mape') is not None)
check('aggregate covers products', fc['aggregate']['products_covered'] > 0)

f0 = fc['forecasts'][0]
check('forecast has components block', 'components' in f0)
check('components expose weekday factors',
      len(f0['components'].get('weekday_factors', {})) == 7)
check('forecast has predictions', len(f0['predictions']) == 30, len(f0['predictions']))
check('predictions are non-negative', all(p['units'] >= 0 for p in f0['predictions']))
check('per-product metrics present', f0['metrics'].get('mape') is not None)
check('per-product metrics report holdout days', f0['metrics'].get('holdout_days', 0) > 0)

status, fc_over = call('GET', '/analytics/demand-forecast/?horizon=500', token=admin_token)
check('horizon clamped to 90', len(fc_over['forecasts'][0]['predictions']) == 90)

status, _ = call('GET', '/analytics/demand-forecast/?product=abc', token=admin_token)
check('non-integer product filter -> 400', status == 400, status)

# ---------------------------------------------------------------- predictions/alerts
print('\n--- Prediction alerts ---')

status, alerts = call('GET', '/analytics/predictions/', token=admin_token)
check('alerts allowed for admin', status == 200, status)
check('alerts report synthetic source', alerts.get('data_source') == 'synthetic')
check('forecast_available is True', alerts.get('forecast_available') is True)

status, _ = call('GET', '/analytics/predictions/', token=customer_token)
check('alerts forbidden for customer (403)', status == 403, status)

# ---------------------------------------------------------------- authz sweep
print('\n--- Authorization sweep (customer must be blocked) ---')

for path in [
    '/analytics/sales/', '/analytics/trending/', '/analytics/inventory/',
    '/analytics/predictions/', '/analytics/demand-forecast/',
    '/products/admin/products/', '/products/admin/categories/',
    '/festivals/admin/kits/', '/orders/admin/orders/',
]:
    status, _ = call('GET', path, token=customer_token)
    check('customer blocked: ' + path, status == 403, 'got %s' % status)

print('\n--- Authorization sweep (admin must be allowed) ---')

for path in [
    '/analytics/sales/', '/analytics/trending/', '/analytics/inventory/',
    '/analytics/predictions/', '/analytics/demand-forecast/',
    '/products/admin/products/', '/products/admin/categories/',
    '/festivals/admin/kits/', '/orders/admin/orders/',
]:
    status, _ = call('GET', path, token=admin_token)
    check('admin allowed: ' + path, status == 200, 'got %s' % status)

# ---------------------------------------------------------------- summary
print('\n' + '=' * 62)
print('RESULT: %d passed, %d failed' % (passed, failed))
if failures:
    print('\nFAILURES:')
    for f in failures:
        print('  - ' + f)
print('=' * 62)

raise SystemExit(1 if failed else 0)
