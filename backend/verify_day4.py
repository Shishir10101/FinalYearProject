"""Day 4 — order status history, password reset, catalogue validation.

Runs against a live server on :8000 through the real HTTP API (no test client),
the same way verify_day2/day3/day3b/day3c do.

What it proves:

1. **Order status history is real.** A fresh order records a ``pending`` event at
   checkout, every admin transition appends one more, each step of the timeline
   carries a genuine timestamp, and re-saving an unchanged status adds nothing.
   Before Day 4 the timeline was derived from ``Order.status`` and every step was
   permanently undated.
2. **Password reset actually works.** The new password authenticates, the old one
   stops working, a link works exactly once, and an unknown address is
   indistinguishable from a known one.
3. **Three data-integrity holes are closed.** Negative price, negative delivery
   fee, and duplicate category name are all refused with a field-level error.
4. **Authorization was not weakened.** A customer is still refused on every admin
   surface.

Cleanup: this script creates one order and one user. Both are marked, and both
are removable:

    ./venv/Scripts/python.exe manage.py purge_verification_orders
    ./venv/Scripts/python.exe manage.py purge_verification_users

Usage:  ./venv/Scripts/python.exe verify_day4.py
"""

import json
import os
import urllib.error
import urllib.request
import uuid

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
FAILURES = []

ORDER_MARKER = 'verify_day4.py'
# Unique per run. A fixed name collides on a re-run (register returns 400 "already
# exists") and the script silently skips its password-reset section, which looks
# like a product failure but is a verifier bug.
PROBE_SUFFIX = uuid.uuid4().hex[:8]
PROBE_USERNAME = f'verifyday4probe{PROBE_SUFFIX}'
PROBE_EMAIL = f'verifyday4probe{PROBE_SUFFIX}@example.com'
PROBE_OLD_PASSWORD = 'ProbeOldPass123'
PROBE_NEW_PASSWORD = 'ProbeNewPass456'


SKIPPED = 0


def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {label}')
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f'  FAIL  {label}  {detail}')


def skip(label, reason):
    """A check that could not run for an environmental reason.

    The password-reset endpoints are throttled at 10/min per IP, and a full
    verification sweep exceeds that inside a minute. A 429 there means the throttle
    is working, so it is reported as a skip rather than a failure — otherwise the
    suite becomes order-dependent and reports a product bug that is not one.
    """
    global SKIPPED
    SKIPPED += 1
    print(f'  SKIP  {label}  ({reason})')


def throttled(status, body):
    return status == 429 or (isinstance(body, dict) and 'throttl' in json.dumps(body).lower())


def section(title):
    print(f'\n=== {title} ===')


def request(method, path, token=None, body=None, timeout=25):
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
    except Exception as exc:  # noqa: BLE001 - reported as a check failure
        return 0, str(exc)


def login(username, password):
    status, body = request('POST', '/api/auth/login/', body={
        'username': username, 'password': password,
    })
    if status != 200 or not isinstance(body, dict) or 'access' not in body:
        return None
    return body['access']


def steps_by_key(order):
    return {s['key']: s for s in order['timeline']['steps']}


# ---------------------------------------------------------------- status history

def test_status_history(admin_token, customer_token):
    section('Order status history')

    status, products = request('GET', '/api/products/?page_size=100')
    check('product list reachable', status == 200, f'status={status}')
    product = products['results'][0]

    status, _ = request('POST', '/api/orders/cart/add/', customer_token,
                        {'product_id': product['id'], 'quantity': 1})
    check('add to cart', status == 200, f'status={status}')

    status, order = request('POST', '/api/orders/checkout/', customer_token, {
        'shipping_address': 'E2E Status History Address',
        'shipping_city': 'kathmandu',
        'phone': '9800000000',
        'payment_method': 'cod',
        'notes': ORDER_MARKER,
    })
    check('checkout creates the order', status == 201, f'status={status} body={order}')
    if status != 201:
        return None
    order_id = order['id']

    # --- the placed step is dated
    timeline = order['timeline']
    placed = steps_by_key(order)['pending']
    check('placed step has a real timestamp', bool(placed.get('at')), f'at={placed.get("at")}')
    check('future steps are NOT invented',
          all(steps_by_key(order)[k].get('at') is None
              for k in ['confirmed', 'processing', 'shipped', 'delivered']))
    check('history starts with the placement',
          [h['status'] for h in timeline['history']] == ['pending'],
          f"history={[h['status'] for h in timeline['history']]}")
    check('timeline reports not-terminal', timeline['is_terminal'] is False)

    # --- every admin transition appends exactly one dated event
    seen_times = [placed['at']]
    for target in ['confirmed', 'processing', 'shipped', 'delivered']:
        status, _ = request('PATCH', f'/api/orders/admin/orders/{order_id}/',
                            admin_token, {'status': target})
        check(f'admin sets status={target}', status == 200, f'status={status}')

        status, fetched = request('GET', f'/api/orders/{order_id}/', customer_token)
        check(f'  order reads back as {target}', fetched.get('status') == target,
              f"status={fetched.get('status')}")

        step = steps_by_key(fetched)[target]
        check(f'  {target} step is dated', bool(step.get('at')), f'at={step.get("at")}')
        if step.get('at'):
            check(f'  {target} timestamp is later than the previous step',
                  step['at'] > seen_times[-1],
                  f"{step['at']} <= {seen_times[-1]}")
            seen_times.append(step['at'])

        expected_len = 1 + ['confirmed', 'processing', 'shipped', 'delivered'].index(target) + 1
        actual = len(fetched['timeline']['history'])
        check(f'  history grew to {expected_len}', actual == expected_len, f'len={actual}')

    status, fetched = request('GET', f'/api/orders/{order_id}/', customer_token)
    check('delivered order is terminal', fetched['timeline']['is_terminal'] is True)
    check('delivered step state is done',
          steps_by_key(fetched)['delivered']['state'] == 'done')
    check('all five steps are dated',
          all(s.get('at') for s in fetched['timeline']['steps']),
          f"steps={[s.get('at') for s in fetched['timeline']['steps']]}")

    # --- idempotent re-save must not inflate history
    before = len(fetched['timeline']['history'])
    request('PATCH', f'/api/orders/admin/orders/{order_id}/', admin_token,
            {'status': 'delivered'})
    request('PATCH', f'/api/orders/admin/orders/{order_id}/', admin_token,
            {'status': 'delivered'})
    _, after = request('GET', f'/api/orders/{order_id}/', customer_token)
    check('re-saving the same status adds no history',
          len(after['timeline']['history']) == before,
          f"{before} -> {len(after['timeline']['history'])}")

    # --- payment_status alone must not create a status event
    request('PATCH', f'/api/orders/admin/orders/{order_id}/', admin_token,
            {'payment_status': 'paid'})
    _, after = request('GET', f'/api/orders/{order_id}/', customer_token)
    check('payment_status change adds no status event',
          len(after['timeline']['history']) == before)

    # --- cancelled is its own two-step timeline
    status, _ = request('PATCH', f'/api/orders/admin/orders/{order_id}/',
                        admin_token, {'status': 'cancelled'})
    _, cancelled = request('GET', f'/api/orders/{order_id}/', customer_token)
    keys = [s['key'] for s in cancelled['timeline']['steps']]
    check('cancelled timeline is pending + cancelled', keys == ['pending', 'cancelled'],
          f'keys={keys}')
    check('cancelled is terminal', cancelled['timeline']['is_terminal'] is True)
    check('cancellation is dated',
          bool(steps_by_key(cancelled)['cancelled'].get('at')))

    # --- history must not leak internal notes or staff identity
    blob = json.dumps(cancelled['timeline'])
    check('timeline leaks no note field', '"note"' not in blob)
    check('timeline leaks no changed_by field', 'changed_by' not in blob)

    return order_id


# ---------------------------------------------------------------- password reset

def test_password_reset():
    section('Password reset')

    status, body = request('POST', '/api/auth/register/', body={
        'username': PROBE_USERNAME,
        'email': PROBE_EMAIL,
        'password': PROBE_OLD_PASSWORD,
        'password2': PROBE_OLD_PASSWORD,
        'first_name': 'Probe',
    })
    check('register a throwaway account', status == 201, f'status={status} body={body}')
    if status != 201:
        return

    check('throwaway account can log in',
          login(PROBE_USERNAME, PROBE_OLD_PASSWORD) is not None)

    # --- enumeration resistance, measured on the production configuration shape
    status_known, known = request('POST', '/api/auth/password-reset/',
                                  body={'email': PROBE_EMAIL})
    if throttled(status_known, known):
        # This section makes about ten calls to a 10/min-per-IP endpoint, so a
        # back-to-back sweep exhausts it. Bail out once, clearly, instead of
        # reporting ten failures that are all the same 429.
        skip('the whole password-reset section',
             'rate limited (10/min per IP) — re-run after a minute')
        return
    status_unknown, unknown = request('POST', '/api/auth/password-reset/',
                                      body={'email': 'definitely-not-registered@example.com'})
    check('known address returns 200', status_known == 200, f'status={status_known}')
    check('unknown address returns 200', status_unknown == 200, f'status={status_unknown}')
    check('both share the same generic message',
          known.get('message') == unknown.get('message'),
          f"{known.get('message')!r} vs {unknown.get('message')!r}")
    check('unknown address never receives a link', 'reset_url' not in unknown)

    reset_url = known.get('reset_url')
    check('a reset link is produced', bool(reset_url), f'url={reset_url}')
    if not reset_url:
        return

    query = reset_url.split('?', 1)[1]
    uid = query.split('uid=')[1].split('&')[0]
    token = query.split('token=')[1]

    # --- mismatched confirmation is refused
    status, body = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': token,
        'new_password': PROBE_NEW_PASSWORD, 'new_password2': 'SomethingElse123',
    })
    check('mismatched passwords refused', status == 400, f'status={status}')
    check('mismatch reports the field', 'new_password2' in (body or {}), f'body={body}')

    # --- weak password is refused by Django's validators
    status, body = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': token,
        'new_password': '123', 'new_password2': '123',
    })
    check('weak password refused', status == 400, f'status={status}')
    check('weak password reports the field', 'new_password' in (body or {}), f'body={body}')

    # --- the real thing
    status, body = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': token,
        'new_password': PROBE_NEW_PASSWORD, 'new_password2': PROBE_NEW_PASSWORD,
    })
    check('valid link resets the password', status == 200, f'status={status} body={body}')

    check('NEW password authenticates',
          login(PROBE_USERNAME, PROBE_NEW_PASSWORD) is not None)
    check('OLD password no longer authenticates',
          login(PROBE_USERNAME, PROBE_OLD_PASSWORD) is None)

    # --- single use
    status, _ = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': token,
        'new_password': 'ThirdAttempt789', 'new_password2': 'ThirdAttempt789',
    })
    check('a used link is refused', status == 400, f'status={status}')
    check('the reused link did not overwrite the password',
          login(PROBE_USERNAME, PROBE_NEW_PASSWORD) is not None)

    # --- a bad uid and a bad token must be indistinguishable
    _, bad_uid = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': 'zzz-not-a-uid', 'token': token,
        'new_password': PROBE_NEW_PASSWORD, 'new_password2': PROBE_NEW_PASSWORD,
    })
    _, bad_token = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': 'clearly-wrong',
        'new_password': PROBE_NEW_PASSWORD, 'new_password2': PROBE_NEW_PASSWORD,
    })
    check('bad uid and bad token are indistinguishable',
          json.dumps(bad_uid, sort_keys=True) == json.dumps(bad_token, sort_keys=True),
          f'{bad_uid} vs {bad_token}')

    check('reset response carries no token or password',
          set((body or {}).keys()) == {'message'}, f'body={body}')


# ---------------------------------------------------------------- validation

def test_catalogue_validation(admin_token):
    section('Catalogue validation')

    status, body = request('POST', '/api/products/admin/products/', admin_token, {
        'name': 'Validation Probe', 'description': 'x', 'price': '-5',
        'stock': 5, 'category': 1, 'unit': 'piece',
    })
    check('negative price refused', status == 400, f'status={status}')
    check('negative price reports the price field',
          isinstance(body, dict) and 'price' in body, f'body={body}')

    status, body = request('POST', '/api/products/admin/areas/', admin_token,
                           {'name': 'Negative Fee Probe', 'delivery_fee': '-50'})
    check('negative delivery fee refused', status == 400, f'status={status}')
    check('negative delivery fee reports the field',
          isinstance(body, dict) and 'delivery_fee' in body, f'body={body}')

    status, body = request('POST', '/api/products/admin/categories/', admin_token,
                           {'name': 'dhoop & agarbatti'})
    check('duplicate category name refused (case-insensitive)',
          status == 400, f'status={status} body={body}')
    check('duplicate category reports the name field',
          isinstance(body, dict) and 'name' in body, f'body={body}')

    status, body = request('POST', '/api/products/admin/categories/', admin_token,
                           {'name': '   '})
    check('blank category name refused', status == 400, f'status={status}')

    # A zero price is legitimate (complimentary prasad), so it must still work.
    status, created = request('POST', '/api/products/admin/products/', admin_token, {
        'name': 'Verify Day4 Zero Price Probe', 'description': 'x', 'price': '0',
        'stock': 5, 'category': 1, 'unit': 'piece',
    })
    check('zero price still allowed', status == 201, f'status={status} body={created}')
    if status == 201:
        # Confirmed to be the row this script just created, so removing it is safe.
        status, _ = request('DELETE',
                            f"/api/products/admin/products/{created['id']}/", admin_token)
        check('probe product cleaned up', status == 204, f'status={status}')


# ---------------------------------------------------------------- authorization

def test_authorization(customer_token, admin_token):
    section('Authorization not weakened')

    admin_endpoints = [
        '/api/products/admin/products/',
        '/api/products/admin/categories/',
        '/api/products/admin/areas/',
        '/api/orders/admin/orders/',
        '/api/festivals/admin/kits/',
        '/api/analytics/sales/',
        '/api/analytics/trending/',
        '/api/analytics/inventory/',
        '/api/analytics/predictions/',
        '/api/analytics/demand-forecast/',
    ]

    for endpoint in admin_endpoints:
        status, _ = request('GET', endpoint, customer_token)
        check(f'customer 403 on {endpoint}', status == 403, f'status={status}')

    for endpoint in admin_endpoints:
        status, _ = request('GET', endpoint, admin_token)
        check(f'admin 200 on {endpoint}', status == 200, f'status={status}')

    status, body = request('POST', '/api/auth/password-reset/', body={'email': 'x'})
    if throttled(status, body):
        skip('password reset rejects a malformed email', 'rate limited (10/min per IP)')
    else:
        check('password reset rejects a malformed email', status == 400, f'status={status}')

    status, _ = request('GET', '/api/orders/')
    check('anonymous cannot list orders', status == 401, f'status={status}')


# ---------------------------------------------------------------- main

def main():
    print(f'Verifying against {BASE}')

    admin_token = login('admin', 'admin123')
    customer_token = login('testuser', 'test1234')

    check('admin can log in', admin_token is not None)
    check('customer can log in', customer_token is not None)
    if not admin_token or not customer_token:
        print('\nCannot continue without both tokens.')
        return 1

    order_id = test_status_history(admin_token, customer_token)
    test_password_reset()
    test_catalogue_validation(admin_token)
    test_authorization(customer_token, admin_token)

    section('Cleanup')
    if order_id:
        # Cancel rather than delete: deleting through the API is not exposed, and
        # purge_verification_orders removes it by marker afterwards.
        request('PATCH', f'/api/orders/admin/orders/{order_id}/', admin_token,
                {'status': 'cancelled'})
        print(f'  order {order_id} left cancelled and marked {ORDER_MARKER!r}')
    print(f'  probe user {PROBE_USERNAME!r} left for purge_verification_users')
    print('  run:  manage.py purge_verification_orders')
    print('        manage.py purge_verification_users')

    print(f'\n{"=" * 60}')
    print(f'  {PASS} passed, {FAIL} failed'
          + (f', {SKIPPED} skipped' if SKIPPED else ''))
    if FAILURES:
        print('  Failed checks:')
        for name in FAILURES:
            print(f'    - {name}')
    print(f'{"=" * 60}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
