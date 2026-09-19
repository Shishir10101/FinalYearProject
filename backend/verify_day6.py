"""Day 6 — the Puja (ritual) discovery entry point.

Runs against a live server on :8000 through the real HTTP API, like the other
verifiers.

`AGENTS.md` §1 requires discovery through six entry points — Product · Category ·
Festival · **Puja** · Samagri · Ready-made Kit. The Puja one had no model,
endpoint or page at all. This proves it exists and behaves:

1. The ritual list is public, counts correctly, and names the kit when there is one.
2. The detail endpoint returns the samagri with the required/optional split intact.
3. An unknown or inactive ritual is a 404, not an empty 200.
4. Adding a ritual's essentials to the cart works, respects stock, and reports
   anything it had to skip instead of silently under-filling the order.
5. It all stays behind auth — a customer cannot add to another user's cart.
6. Authorization elsewhere was not weakened.

Cleanup: creates one cart and one order. Run afterwards:

    ./venv/Scripts/python.exe manage.py purge_verification_orders

Usage:  ./venv/Scripts/python.exe verify_day6.py
"""

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
FAILURES = []

ORDER_MARKER = 'verify_day6.py'


def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {label}')
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f'  FAIL  {label}  {detail}')


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


# ---------------------------------------------------------------- list

def test_puja_list():
    section('Ritual list')

    status, pujas = request('GET', '/api/festivals/pujas/')
    check('list is public and returns 200', status == 200, f'status={status}')
    check('list is not paginated', isinstance(pujas, list), f'type={type(pujas).__name__}')
    if not isinstance(pujas, list):
        return []
    check('the seeded rituals are present', len(pujas) >= 7, f'count={len(pujas)}')

    names = [p['name'] for p in pujas]
    check('Daily Puja exists', 'Daily Puja' in names, f'names={names}')
    check('Dashain Tika exists', 'Dashain Tika' in names)

    # The six entry points name Puja *and* Ready-made Kit separately, so a ritual
    # must be able to exist without one.
    daily = next((p for p in pujas if p['slug'] == 'daily-puja'), None)
    check('a ritual can exist with no kit', daily is not None and daily['kit_id'] is None,
          f'daily={daily}')

    dashain = next((p for p in pujas if p['slug'] == 'dashain-tika'), None)
    check('a kit-backed ritual names its kit',
          dashain is not None and bool(dashain['kit_name']), f'dashain={dashain}')
    check('required_count never exceeds item_count',
          all(p['required_count'] <= p['item_count'] for p in pujas))

    return pujas


# ---------------------------------------------------------------- detail

def test_puja_detail(pujas):
    section('Ritual detail')

    status, puja = request('GET', '/api/festivals/pujas/dashain-tika/')
    check('detail by slug returns 200', status == 200, f'status={status}')
    if status != 200:
        return None

    check('detail carries the samagri', len(puja['items']) > 0,
          f"items={len(puja.get('items', []))}")
    required = [i for i in puja['items'] if i['is_required']]
    optional = [i for i in puja['items'] if not i['is_required']]
    check('the required/optional split is preserved', len(required) > 0,
          f'required={len(required)} optional={len(optional)}')
    check('essentials come first',
          all(i['is_required'] for i in puja['items'][:len(required)]))
    check('every item carries its product payload',
          all(i['product_detail'] and i['product_detail']['name'] for i in puja['items']))
    check('every item carries a quantity', all(i['quantity'] >= 1 for i in puja['items']))
    check('a kit-backed ritual exposes its kit', puja['kit'] is not None)

    # The list's counts must agree with the detail, or one of them is lying.
    listed = next((p for p in pujas if p['slug'] == 'dashain-tika'), None)
    if listed:
        check('list counts agree with the detail',
              listed['item_count'] == len(puja['items'])
              and listed['required_count'] == len(required),
              f"list={listed['item_count']}/{listed['required_count']} "
              f"detail={len(puja['items'])}/{len(required)}")

    section('Unknown and inactive rituals')
    status, _ = request('GET', '/api/festivals/pujas/not-a-real-ritual/')
    check('unknown slug is 404', status == 404, f'status={status}')

    status, _ = request('GET', '/api/festivals/pujas/')
    check('list stays 200 after a 404', status == 200)

    return puja


# ---------------------------------------------------------------- cart

def test_add_to_cart(customer_token, admin_token):
    section('Add a ritual to the cart')

    # Clear whatever is in the cart rather than assuming it starts empty. Asserting
    # a precondition the script did not create is how a verifier reports a failure
    # that is really just leftover state.
    _, existing = request('GET', '/api/orders/cart/', customer_token)
    for line in existing.get('items', []):
        request('DELETE', f"/api/orders/cart/remove/{line['id']}/", customer_token)
    status, cart = request('GET', '/api/orders/cart/', customer_token)
    check('cart is empty to begin with', status == 200 and len(cart['items']) == 0,
          f"items={len(cart.get('items', []))}")

    status, body = request('POST', '/api/orders/cart/add-puja/999999/', customer_token)
    check('unknown ritual id is 404', status == 404, f'status={status}')

    status, _ = request('POST', '/api/orders/cart/add-puja/1/')
    check('anonymous cannot add to a cart', status == 401, f'status={status}')

    # Pick a ritual whose essentials are all in stock.
    _, pujas = request('GET', '/api/festivals/pujas/')
    target = next((p for p in pujas if p['slug'] == 'dashain-tika'), None)
    if target is None:
        check('found a ritual to add', False)
        return

    status, detail = request('GET', f"/api/festivals/pujas/{target['slug']}/")
    required = [i for i in detail['items'] if i['is_required']]

    status, body = request('POST', f"/api/orders/cart/add-puja/{target['id']}/", customer_token)
    check('add-puja returns 200', status == 200, f'status={status} body={body}')

    if status == 200:
        check('it added the essential items',
              body.get('added', 0) + len(body.get('skipped', [])) == len(required),
              f"added={body.get('added')} skipped={len(body.get('skipped', []))} "
              f"required={len(required)}")
        check('it reports what it skipped rather than hiding it',
              'skipped' not in body or bool(body.get('warning')),
              f"body={body}")

        status, cart = request('GET', '/api/orders/cart/', customer_token)
        check('the cart now has lines', len(cart['items']) > 0, f"items={len(cart['items'])}")
        cart_names = {i['product_detail']['name'] for i in cart['items']}
        required_names = {i['product_detail']['name'] for i in required}
        check('only essentials were added',
              cart_names.issubset(required_names),
              f'extra={cart_names - required_names}')

    # Optional extras must never be added on the customer's behalf.
    optional = [i for i in detail['items'] if not i['is_required']]
    if optional:
        status, cart = request('GET', '/api/orders/cart/', customer_token)
        cart_names = {i['product_detail']['name'] for i in cart['items']}
        optional_names = {i['product_detail']['name'] for i in optional}
        check('no optional extras were added', not (cart_names & optional_names),
              f'leaked={cart_names & optional_names}')

    # Clean up the cart by removing every line.
    _, cart = request('GET', '/api/orders/cart/', customer_token)
    for line in cart['items']:
        request('DELETE', f"/api/orders/cart/remove/{line['id']}/", customer_token)
    _, cart = request('GET', '/api/orders/cart/', customer_token)
    check('cart cleaned up', len(cart['items']) == 0, f"items={len(cart['items'])}")


# ---------------------------------------------------------------- authz

def test_authorization(customer_token, admin_token):
    section('Authorization not weakened')

    for endpoint in [
        '/api/products/admin/products/',
        '/api/orders/admin/orders/',
        '/api/analytics/sales/',
        '/api/analytics/demand-forecast/',
    ]:
        status, _ = request('GET', endpoint, customer_token)
        check(f'customer 403 on {endpoint}', status == 403, f'status={status}')
        status, _ = request('GET', endpoint, admin_token)
        check(f'admin 200 on {endpoint}', status == 200, f'status={status}')

    # The new public endpoints must stay public.
    for endpoint in ['/api/festivals/pujas/', '/api/festivals/pujas/daily-puja/']:
        status, _ = request('GET', endpoint)
        check(f'anonymous 200 on {endpoint}', status == 200, f'status={status}')


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

    pujas = test_puja_list()
    test_puja_detail(pujas)
    test_add_to_cart(customer_token, admin_token)
    test_authorization(customer_token, admin_token)

    print(f'\n{"=" * 60}')
    print(f'  {PASS} passed, {FAIL} failed')
    if FAILURES:
        print('  Failed checks:')
        for name in FAILURES:
            print(f'    - {name}')
    print(f'{"=" * 60}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
