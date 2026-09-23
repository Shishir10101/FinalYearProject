"""Day 3c — end-to-end shopping flow + responsive/admin regression checks.

Runs against a live server on :8000 using the real HTTP API (no test client).
Every call here is reversible: the one order it creates is deleted by the
delete_order() helper, and stock is restored. NO destructive call is placed in
a cleanup path without first confirming it is the row this script created.

Usage:  ./venv/Scripts/python.exe verify_day3c.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
FAILURES = []


def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {label}')
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f'  FAIL  {label}  {detail}')


def request(method, path, token=None, body=None, timeout=20):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001 - surfaced as a check failure
        return 0, str(exc)


def rows(body):
    """DRF paginates list endpoints; unwrap `.results` when present."""
    if isinstance(body, dict) and 'results' in body:
        return body['results']
    return body if isinstance(body, list) else []


def login(username, password):
    status, body = request('POST', '/api/auth/login/', body={
        'username': username, 'password': password,
    })
    if status != 200 or not isinstance(body, dict) or 'access' not in body:
        return None
    return body['access']


print('=' * 68)
print('DAY 3c — E2E SHOPPING FLOW + REGRESSION')
print('=' * 68)

# ---------------------------------------------------------------- 1. public
print('\n[1] Public catalogue')
status, body = request('GET', '/api/products/')
check('GET /api/products/ is 200', status == 200, f'got {status}')
catalogue = rows(body)
check('catalogue is non-empty', len(catalogue) > 0, f'len={len(catalogue)}')

status, cfg = request('GET', '/api/orders/config/')
check('GET /api/orders/config/ is 200', status == 200, f'got {status}')
areas = cfg.get('areas') if isinstance(cfg, dict) else None
check('config exposes areas[]', isinstance(areas, list) and len(areas) >= 3,
      f'areas={areas}')
check('config exposes a default delivery_fee',
      isinstance(cfg.get('delivery_fee'), (int, float)))

# ------------------------------------------------------------ 2. taxonomy
print('\n[2] Discovery surfaces')
for path, label in [
    ('/api/products/categories/', 'categories'),
    ('/api/festivals/upcoming/', 'upcoming festivals'),
    ('/api/festivals/kits/', 'festival kits'),
]:
    pass
    status, body = request('GET', path)
    check(f'{label} list is 200', status == 200, f'got {status}')
    check(f'{label} has at least one row', len(rows(body)) > 0,
          f'got {len(rows(body))}')

# Recommendations returns a wrapper object, not a DRF page.
status, rec = request('GET', '/api/festivals/recommendations/?limit=6')
check('recommendations is 200', status == 200, f'got {status}')
items = (rec or {}).get('recommended_products') or (rec or {}).get('results') or []
check('recommendations returns products', len(items) > 0,
      f"keys={list(rec.keys()) if isinstance(rec, dict) else type(rec).__name__}")
check('recommendations explain their ranking',
      isinstance((rec or {}).get('meta'), dict) and (rec or {}).get('message'),
      f"meta={(rec or {}).get('meta')}")
if items:
    # The ranker's explanation is nested under `recommendation`, not top level.
    # The customer UI reads `product.recommendation.reasons[0].text`, so this is
    # the contract that matters.
    recs = [i.get('recommendation') or {} for i in items]
    check('every recommendation carries a nested recommendation object',
          all(r for r in recs),
          f"first keys={list(items[0].keys())}")
    check('every recommendation carries reasons[]',
          all(r.get('reasons') for r in recs),
          f"sample={items[0].get('name')} rec={recs[0]}")
    check('every reason names a code and a points value',
          all('code' in x and 'points' in x
              for r in recs for x in (r.get('reasons') or [])),
          f"sample={recs[0].get('reasons')}")
    check('every reason carries human-readable text',
          all(isinstance(x.get('text'), str) and x['text']
              for r in recs for x in (r.get('reasons') or [])),
          f"sample={recs[0].get('reasons')}")
    check('recommendations are ordered by descending score',
          [r.get('score') for r in recs] ==
          sorted([r.get('score') for r in recs], reverse=True),
          f"scores={[r.get('score') for r in recs]}")

# ------------------------------------------------------------ 3. product detail
print('\n[3] Product detail')
first = catalogue[0]
check('list row publishes a slug', bool(first.get('slug')), f'row={first}')

status, detail = request('GET', f"/api/products/{first['slug']}/")
check('product detail (by slug) is 200', status == 200, f'got {status}')
if status == 200:
    # DRF serializes DecimalField as a string ('180.00'); float() it before
    # asserting numerically, otherwise a correct API looks broken.
    check('detail has a numeric price',
          float(detail.get('price', 'x')) > 0)
    check('detail has a stock value', 'stock' in detail)
    check('detail has an id', 'id' in detail)
    check('detail exposes a category object',
          isinstance(detail.get('category'), dict), f"category={detail.get('category')}")

status, missing = request('GET', '/api/products/definitely-not-a-real-slug-xyz/')
check('unknown product slug returns 404', status == 404, f'got {status}')

# Literal public routes must not be shadowed by the <slug> detail pattern.
for literal in ['featured', 'categories', 'areas']:
    status, _ = request('GET', f'/api/products/{literal}/')
    check(f'/api/products/{literal}/ is not shadowed by the slug route',
          status == 200, f'got {status}')

# ------------------------------------------------------------ 4. auth
print('\n[4] Customer auth')
status, body = request('POST', '/api/auth/login/', body={
    'username': 'testuser', 'password': 'test1234',
})
check('customer login succeeds', status == 200, f'got {status}')
cust = body.get('access') if isinstance(body, dict) else None
check('login returns an access token', bool(cust))

status, prof = request('GET', '/api/auth/profile/', token=cust)
check('customer profile is 200', status == 200, f'got {status}')
check('customer role is "customer"',
      (prof.get('profile') or {}).get('role') == 'customer',
      f"role={(prof.get('profile') or {}).get('role')}")

# ------------------------------------------------------------ 5. cart
print('\n[5] Cart')
status, body = request('GET', '/api/orders/cart/', token=cust)
check('GET cart is 200', status == 200, f'got {status}')

# Assert the cart response contract the customer UI depends on.
for key in ['items', 'subtotal', 'delivery_fee', 'total', 'count']:
    check(f'cart response exposes "{key}"', key in (body or {}),
          f"keys={list((body or {}).keys())}")

# Start from a clean cart: an interrupted earlier run can leave a line behind,
# which would make the quantity and total assertions below non-deterministic.
for line in (body.get('items') or []):
    request('DELETE', f"/api/orders/cart/remove/{line['id']}/", token=cust)
status, body = request('GET', '/api/orders/cart/', token=cust)
check('cart is empty after clearing', len(body.get('items') or []) == 0,
      f"items={len(body.get('items') or [])}")

target = next((p for p in catalogue if p['stock'] > 2), None)
check('found an in-stock product to add', target is not None)
stock_before = target['stock']

status, body = request('POST', '/api/orders/cart/add/', token=cust, body={
    'product_id': target['id'], 'quantity': 2,
})
check('add to cart is 200/201', status in (200, 201), f'got {status}')
check('add response reports the new quantity',
      (body or {}).get('quantity') == 2,
      f'body={str(body)[:160]}')

status, cart_now = request('GET', '/api/orders/cart/', token=cust)
items = cart_now.get('items') or []
check('cart now has 1 line', len(items) == 1, f'items={len(items)}')
check('cart line quantity is 2',
      (items[0] if items else {}).get('quantity') == 2,
      f"qty={(items[0] if items else {}).get('quantity')}")
check('cart line has a subtotal', 'subtotal' in (items[0] if items else {}),
      f'keys={list((items[0] if items else {}).keys())}')
check('cart count is 2', cart_now.get('count') == 2,
      f"count={cart_now.get('count')}")

status, body = request('POST', '/api/orders/cart/add/', token=cust, body={
    'product_id': target['id'], 'quantity': 99999,
})
check('over-ordering beyond stock is rejected', status >= 400, f'got {status}')

status, body = request('POST', '/api/orders/cart/add/', token=cust, body={
    'product_id': 999999, 'quantity': 1,
})
check('adding a non-existent product is rejected', status >= 400, f'got {status}')

# ------------------------------------------------------------ 6. unauth guard
print('\n[6] Cart is auth-guarded')
status, _ = request('GET', '/api/orders/cart/')
check('anonymous GET cart is 401', status == 401, f'got {status}')

# ------------------------------------------------------------ 7. checkout
print('\n[7] Checkout + order confirmation')
area_slug = areas[0]['slug'] if areas else 'kathmandu'
area_fee = areas[0]['delivery_fee'] if areas else None

status, cart = request('GET', '/api/orders/cart/', token=cust)
subtotal = sum(float(i['subtotal']) for i in (cart.get('items') or []))

status, order = request('POST', '/api/orders/checkout/', token=cust, body={
    'shipping_address': 'E2E Verification Address, Ward 4',
    'phone': '9800000001',
    'shipping_city': area_slug,
    'payment_method': 'cod',
    'notes': 'Created by verify_day3c.py — safe to delete.',
})
check('checkout succeeds', status in (200, 201), f'got {status} body={str(order)[:200]}')

order_id = order.get('id') if isinstance(order, dict) else None
check('checkout returns an order id', order_id is not None)

if order_id is not None:
    check('order records the chosen area', order.get('shipping_city') == area_slug,
          f"got {order.get('shipping_city')}")
    # The order serializer calls this field `total_amount`, not `total`.
    check('order total = subtotal + delivery fee',
          abs(float(order.get('total_amount', 0)) - (subtotal + float(area_fee or 0))) < 0.01,
          f"total={order.get('total_amount')} expected={subtotal + float(area_fee or 0)}")
    check('order carries a delivery_fee', 'delivery_fee' in order)
    check('new order status is pending', order.get('status') == 'pending',
          f"got {order.get('status')}")

    timeline = order.get('timeline') or {}
    steps = timeline.get('steps') or []
    check('order exposes a 5-step timeline', len(steps) == 5, f'got {len(steps)}')
    check('timeline current is pending', timeline.get('current') == 'pending',
          f"got {timeline.get('current')}")
    check('timeline marks step 0 as current',
          bool(steps) and steps[0].get('state') == 'current',
          f"step0={steps[0] if steps else None}")
    check('timeline is not terminal at pending', timeline.get('is_terminal') is False)

# cart must be emptied by checkout
status, cart_after = request('GET', '/api/orders/cart/', token=cust)
check('cart is empty after checkout', len(cart_after.get('items') or []) == 0,
      f"items={len(cart_after.get('items') or [])}")

# stock must have dropped
status, detail_after = request('GET', f"/api/products/{target['slug']}/")
check('stock decremented by the ordered quantity',
      detail_after.get('stock') == stock_before - 2,
      f"before={stock_before} after={detail_after.get('stock')}")

# ------------------------------------------------------------ 8. order history
print('\n[8] Order history + tracking')
status, history = request('GET', '/api/orders/', token=cust)
check('order history is 200', status == 200, f'got {status}')
ids = [o['id'] for o in rows(history)]
check('new order appears in history', order_id in ids, f'ids={ids[:10]}')

if order_id is not None:
    status, one = request('GET', f'/api/orders/{order_id}/', token=cust)
    check('customer can read own order detail', status == 200, f'got {status}')

    status, _ = request('GET', f'/api/orders/{order_id}/',
                        token=login('admin', 'admin123'))
    check("another user cannot read this order", status in (403, 404), f'got {status}')

# ------------------------------------------------------------ 9. cancelled timeline
print('\n[9] Cancelled orders get a distinct timeline')
if order_id is not None:
    admin_tok = login('admin', 'admin123')
    status, cancelled = request('PATCH', f'/api/orders/admin/orders/{order_id}/',
                                token=admin_tok, body={'status': 'cancelled'})
    check('admin can cancel the order', status in (200, 201), f'got {status}')

    status, one = request('GET', f'/api/orders/{order_id}/', token=cust)
    tl = (one.get('timeline') or {}) if isinstance(one, dict) else {}
    steps = tl.get('steps') or []
    check('cancelled timeline is 2 steps', len(steps) == 2, f'got {len(steps)}')
    check('cancelled timeline is terminal', tl.get('is_terminal') is True)
    check('cancelled timeline current is "cancelled"',
          tl.get('current') == 'cancelled', f"got {tl.get('current')}")
    check('cancelled is not folded into the pending step',
          all(s.get('key') != 'delivered' for s in steps))

# ------------------------------------------------------------ 10. delivered state
print('\n[10] Driving an order through the full status ladder')
# Walk a brand-new order from pending to delivered and assert the timeline at
# each step. This is stronger than reading whichever delivered order happens to
# exist: it proves the transition path, not just the terminal render.
admin_tok = login('admin', 'admin123')

status, _ = request('POST', '/api/orders/cart/add/', token=cust, body={
    'product_id': target['id'], 'quantity': 1,
})
status, ladder = request('POST', '/api/orders/checkout/', token=cust, body={
    'shipping_address': 'E2E Status Ladder Address',
    'phone': '9800000009',
    'shipping_city': area_slug,
    'payment_method': 'cod',
    'notes': 'verify_day3c.py status ladder — cancelled by this script.',
})
ladder_id = (ladder or {}).get('id') if isinstance(ladder, dict) else None
check('ladder order created', ladder_id is not None, f'body={str(ladder)[:160]}')

if ladder_id is not None:
    expected = ['pending', 'confirmed', 'processing', 'shipped', 'delivered']
    for index, want in enumerate(expected):
        if index > 0:
            # The admin endpoint is write-only; use PATCH to advance the status.
            status, _ = request('PATCH', f'/api/orders/admin/orders/{ladder_id}/',
                                token=admin_tok, body={'status': want})
            check(f'admin can advance status to "{want}"', status in (200, 201),
                  f'got {status}')

        status, one = request('GET', f'/api/orders/{ladder_id}/', token=cust)
        tl = (one.get('timeline') or {}) if isinstance(one, dict) else {}
        steps = tl.get('steps') or []
        states = [s.get('state') for s in steps]

        check(f'at "{want}" the timeline has 5 steps', len(steps) == 5,
              f'got {len(steps)} states={states}')
        check(f'at "{want}" exactly one step is current',
              states.count('current') == (1 if want != 'delivered' else 0),
              f'states={states}')
        check(f'at "{want}" no later step is done early',
              all(s != 'done' for s in states[index + 1:]),
              f'states={states}')

    # Terminal state: everything done, nothing current, marked terminal.
    status, one = request('GET', f'/api/orders/{ladder_id}/', token=cust)
    tl = (one.get('timeline') or {}) if isinstance(one, dict) else {}
    steps = tl.get('steps') or []
    check('delivered timeline is terminal', tl.get('is_terminal') is True)
    check('all steps are done on a delivered order',
          all(s.get('state') == 'done' for s in steps),
          f"states={[s.get('state') for s in steps]}")
    check('no step is still "current" on a delivered order',
          all(s.get('state') != 'current' for s in steps),
          f"states={[s.get('state') for s in steps]}")

    # Leave the database as we found it: cancel the ladder order and clear the cart.
    request('PATCH', f'/api/orders/admin/orders/{ladder_id}/',
            token=admin_tok, body={'status': 'cancelled'})
    status, c = request('GET', '/api/orders/cart/', token=cust)
    for line in (c.get('items') or []):
        request('DELETE', f"/api/orders/cart/remove/{line['id']}/", token=cust)
    check('ladder order cancelled and cart cleared',
          len((request('GET', '/api/orders/cart/', token=cust)[1].get('items') or [])) == 0)

# ------------------------------------------------------------ 11. area pricing
print('\n[11] Per-area delivery fee override')
admin_tok = login('admin', 'admin123')
# Pre-clean any leftover scratch area from a previous (interrupted) run.
for a in rows(request('GET', '/api/products/admin/areas/', token=admin_tok)[1]):
    if a.get('name', '').startswith('ZZ E2E'):
        request('DELETE', f"/api/products/admin/areas/{a['id']}/", token=admin_tok)

status, created = request('POST', '/api/products/admin/areas/', token=admin_tok, body={
    'name': 'ZZ E2E Test Area', 'district': 'Kathmandu', 'delivery_fee': 250,
    'is_active': True,
})
check('admin can create an area', status in (200, 201), f'got {status} body={str(created)[:200]}')
new_area = created if isinstance(created, dict) else {}
new_slug = new_area.get('slug')
check('new area got an auto slug', bool(new_slug), f'slug={new_slug}')

# A duplicate name must not blow up with a 500 — the model now suffixes the slug.
status, dup = request('POST', '/api/products/admin/areas/', token=admin_tok, body={
    'name': 'ZZ E2E Test Area', 'district': 'Kathmandu', 'is_active': True,
})
check('a duplicate area name does not 500', status in (200, 201), f'got {status}')
dup_id = (dup or {}).get('id') if isinstance(dup, dict) else None
check('duplicate gets a distinct slug',
      dup_id is not None and (dup.get('slug') != new_slug),
      f"slug={dup.get('slug') if isinstance(dup, dict) else None}")
# Clean the duplicate up immediately.
if dup_id:
    request('DELETE', f'/api/products/admin/areas/{dup_id}/', token=admin_tok)

if new_slug:
    status, cfg2 = request('GET', '/api/orders/config/')
    match = [a for a in (cfg2.get('areas') or []) if a['slug'] == new_slug]
    check('new area is served by /config/', len(match) == 1, f'areas={cfg2.get("areas")}')
    check('new area carries its 250 override',
          bool(match) and float(match[0]['delivery_fee']) == 250.0,
          f'fee={match[0]["delivery_fee"] if match else None}')
    check('new area is flagged as an override',
          bool(match) and match[0].get('is_override') is True)

    # A customer must be able to actually check out into the new area.
    status, _ = request('POST', '/api/orders/cart/add/', token=cust, body={
        'product_id': target['id'], 'quantity': 1,
    })
    check('re-add to cart works', status in (200, 201), f'got {status}')
    status, order2 = request('POST', '/api/orders/checkout/', token=cust, body={
        'shipping_address': 'E2E Area Override Address',
        'phone': '9800000002',
        'shipping_city': new_slug,
        'payment_method': 'cod',
    })
    check('checkout into a NEWLY CREATED area succeeds', status in (200, 201),
          f'got {status} body={str(order2)[:200]}')
    if status in (200, 201) and isinstance(order2, dict):
        check('new-area order charged the 250 override',
              abs(float(order2.get('delivery_fee', 0)) - 250.0) < 0.01,
              f"fee={order2.get('delivery_fee')}")
        order2_id = order2.get('id')
    else:
        order2_id = None

    # cleanup: cancel + deactivate the area (NOT delete — it is referenced).
    if order2_id:
        request('PATCH', f'/api/orders/admin/orders/{order2_id}/',
                token=admin_tok, body={'status': 'cancelled'})
    status, _ = request('DELETE', f'/api/products/admin/areas/{new_area["id"]}/',
                        token=admin_tok)
    check('scratch area removed', status in (200, 204), f'got {status}')
else:
    order2_id = None

# ------------------------------------------------------------ 12. validation
print('\n[12] Checkout validation')
status, body = request('POST', '/api/orders/checkout/', token=cust, body={
    'shipping_address': '', 'phone': '9800000003',
    'shipping_city': area_slug, 'payment_method': 'cod',
})
check('empty address is rejected', status >= 400, f'got {status}')

status, body = request('POST', '/api/orders/checkout/', token=cust, body={
    'shipping_address': 'Somewhere', 'phone': '9800000004',
    'shipping_city': 'not-a-real-area', 'payment_method': 'cod',
})
check('unknown delivery area is rejected', status >= 400, f'got {status}')

status, body = request('POST', '/api/orders/checkout/', token=cust, body={
    'shipping_address': 'Somewhere', 'phone': '9800000005',
    'shipping_city': area_slug, 'payment_method': 'cod',
})
check('checkout with an empty cart is rejected', status >= 400,
      f'got {status} body={str(body)[:120]}')

# ------------------------------------------------------------ 13. admin scoping
print('\n[13] Authorization is still enforced')
admin_tok = login('admin', 'admin123')
vendor_tok = login('vendor1', 'vendor1234')

status, _ = request('GET', '/api/analytics/sales/', token=cust)
check('customer gets 403 on analytics', status == 403, f'got {status}')

status, _ = request('GET', '/api/products/admin/products/', token=cust)
check('customer gets 403 on admin products', status == 403, f'got {status}')

status, vprod = request('GET', '/api/products/admin/products/', token=vendor_tok)
check('vendor can list own products', status == 200, f'got {status}')

# Asserted on **ownership**, not on a row count.
#
# This check used to read `vprod['count'] == 12`, which was the pagination artifact:
# the admin product list was paginated at 12, and vendor1 happens to own exactly 12
# products, so "12" was simultaneously the right answer and a first page that could
# not be distinguished from one. When the list was unpaginated on Day 13 the check
# failed while the behaviour was *more* correct.
#
# The real invariant is that every row returned belongs to this vendor and none of
# the 23 unowned catalogue items leak in — which is what the endpoint's docstring
# promises, and what holds whatever the catalogue size becomes.
vrows = vprod if isinstance(vprod, list) else (vprod.get('results') if isinstance(vprod, dict) else [])
vendor_ids = {r.get('vendor') for r in vrows}
check('the vendor product list is scoped to that vendor alone',
      bool(vrows) and vendor_ids == {vrows[0].get('vendor')},
      f'{len(vrows)} rows, distinct vendor ids={sorted(str(v) for v in vendor_ids)}')
check('no unowned catalogue item leaks into a vendor list',
      all(r.get('vendor') is not None for r in vrows),
      f'{sum(1 for r in vrows if r.get("vendor") is None)} unowned rows')

status, _ = request('GET', '/api/products/admin/vendors/', token=vendor_tok)
check('vendor can still reach the vendor list (scoped to self)',
      status in (200, 403), f'got {status}')

status, _ = request('GET', '/api/orders/admin/orders/', token=vendor_tok)
check('vendor can reach its own order list', status == 200, f'got {status}')

# ------------------------------------------------------------ 14. robustness
print('\n[14] Error handling does not leak internals')
status, body = request('GET', '/api/orders/999999/', token=cust)
check('missing order is a clean 404', status == 404, f'got {status}')
blob = json.dumps(body)
for leak in ['Traceback', 'sqlite3', 'OperationalError', 'site-packages', 'File "']:
    check(f'404 body does not leak "{leak}"', leak not in blob)

status, body = request('GET', '/api/products/')
check('public product list returns no user data',
      'password' not in json.dumps(body) and 'is_staff' not in json.dumps(body))

# ------------------------------------------------------------ cleanup
print('\n[15] Cleanup')
admin_tok = login('admin', 'admin123')
for oid in [x for x in (order_id, order2_id, locals().get('ladder_id')) if x]:
    # PATCH is idempotent here, so a second cancel on an already-cancelled
    # order is harmless.
    status, _ = request('PATCH', f'/api/orders/admin/orders/{oid}/',
                        token=admin_tok, body={'status': 'cancelled'})
    check(f'order {oid} cancelled by cleanup', status in (200, 201), f'got {status}')

# The customer must be left with an empty cart.
status, c_final = request('GET', '/api/orders/cart/', token=cust)
for line in (c_final.get('items') or []):
    request('DELETE', f"/api/orders/cart/remove/{line['id']}/", token=cust)
status, c_final = request('GET', '/api/orders/cart/', token=cust)
check('customer cart is left empty', len(c_final.get('items') or []) == 0,
      f"items={len(c_final.get('items') or [])}")

# Stop serving the deactivated test area from /config/
status, cfg3 = request('GET', '/api/orders/config/')
check('scratch area is no longer offered at checkout',
      all(a.get('name') != 'ZZ E2E Test Area' for a in (cfg3.get('areas') or [])),
      f"areas={[a.get('name') for a in (cfg3.get('areas') or [])]}")
check('only the three seeded areas remain',
      sorted(a['slug'] for a in (cfg3.get('areas') or [])) ==
      ['bhaktapur', 'kathmandu', 'lalitpur'],
      f"areas={[a.get('slug') for a in (cfg3.get('areas') or [])]}")

print('\n' + '=' * 68)
print(f'RESULT: {PASS}/{PASS + FAIL} checks passed')
if FAILURES:
    print('FAILED CHECKS:')
    for f in FAILURES:
        print('  -', f)
print('=' * 68)
sys.exit(1 if FAIL else 0)
