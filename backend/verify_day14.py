"""Day 14 — the mocked payment gateways now say so, over the real HTTP API.

One narrow, high-value thing: `POST /orders/checkout/` handles an `esewa` or `khalti`
order by marking it `paid` and `confirmed` **without contacting a gateway**. That is a
reasonable demo shortcut. What was not reasonable is that nothing anywhere told the
customer — the checkout screen offered eSewa and Khalti as ordinary choices, and the
order detail then showed a green `paid` badge for a transaction that never happened.

`docs/FEATURES.md` §6.1 and `docs/DEVELOPMENT-ROADMAP.md` (P2) both named this as the
risk: *"must be labelled as mocked"*. This script is the live proof that it now is, and
— just as importantly — that the label is **not** applied to `cod`, which really is
collected on delivery. A disclosure applied to everything is not a disclosure, so both
directions are asserted.

The single source of truth is `orders.models.PAYMENT_METHODS_ARE_MOCKED`. This script
never hardcodes which methods are fake; it reads the expectation from that constant and
holds the API to it. If someone flips a value when a real integration lands, these
checks follow automatically instead of going stale.

What it is careful about:

* **It owns what it asserts.** The eSewa order and the COD order are both placed by this
  script, with a marker in `notes`, so it never reads a fixture it did not create.
* **It reads before it asserts.** The product it buys is looked up from the live
  catalogue and its stock restored by the purge, not assumed.
* **It checks the audit trail, not just the payload.** A flag on the response is easy; the
  status history is what a person would actually read six months later.

Writes rows. Clean up afterwards:

    ./venv/Scripts/python.exe manage.py purge_verification_orders

Usage:  ./venv/Scripts/python.exe verify_day14.py
"""

import json
import os
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
SKIP = 0
FAILURES = []

# Every order this script places carries this marker, so `purge_verification_orders`
# removes exactly these and nothing else. It matches MARKERS in that command.
ORDER_MARKER = 'verify_day14_disclosure.py'

LOGIN = {'username': 'testuser', 'password': 'test1234'}


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
    global SKIP
    SKIP += 1
    print(f'  SKIP  {label}  ({reason})')


def section(title):
    print(f'\n=== {title} ===')


def request(method, path, token=None, body=None, timeout=30):
    """A JSON request. Returns `(status, parsed_body_or_text)`."""
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode() or 'null'
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() or 'null'
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001 - a verifier should report, not crash
        return 0, str(exc)


def main():
    section('The expectation itself is read from the model, not restated here')

    # Import directly so the verifier cannot drift from the app. This is the whole
    # design: one constant decides, everything downstream follows.
    try:
        import django
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
        django.setup()
        from orders.models import PAYMENT_METHODS_ARE_MOCKED as MOCKED
    except Exception as exc:  # noqa: BLE001
        print(f'  Could not import the constant ({exc}); run from backend/.')
        return 2

    check('the constant declares the mocked methods',
        isinstance(MOCKED, dict) and MOCKED, repr(MOCKED))
    mocked_values = sorted(k for k, v in MOCKED.items() if v)
    real_values = sorted(k for k, v in MOCKED.items() if not v)
    print(f'        mocked={mocked_values}  real={real_values}')

    section('GET /orders/config/ publishes the honesty flags')

    status, cfg = request('GET', '/api/orders/config/')
    check('the config endpoint is public and healthy', status == 200, f'status={status}')
    if status != 200:
        return 1

    methods = {m['value']: m for m in cfg.get('payment_methods', [])}
    check('every method is listed with a flag',
        set(methods) == set(MOCKED), f'api={sorted(methods)} constant={sorted(MOCKED)}')

    for value, expected in sorted(MOCKED.items()):
        actual = methods.get(value, {}).get('is_mocked')
        check(f'{value} is reported as mocked={expected}', actual is expected,
            f'api said {actual}, the constant says {expected}')

    check('the API and the constant agree that something is mocked',
        cfg.get('any_payment_mocked') == any(MOCKED.values()),
        f"api={cfg.get('any_payment_mocked')}")

    section('An order paid through a simulated gateway is flagged as such')

    status, login = request('POST', '/api/auth/login/', body=LOGIN)
    if status != 200:
        print(f'  Cannot log in ({status}); is the seeded data present?')
        return 2
    token = login['access']

    status, catalogue = request('GET', '/api/products/')
    products = catalogue.get('results', catalogue) if isinstance(catalogue, dict) else []
    if not products:
        print('  No products in the catalogue; cannot place an order.')
        return 2
    # Buy something the seed leaves in plentiful stock, so a temporary decrement
    # cannot push a product into a false low-stock state mid-run.
    product = max(products, key=lambda p: p.get('stock') or 0)
    print(f'        buying product {product["id"]} ({product["name"]}) stock={product["stock"]}')

    def place(payment_method):
        request('POST', '/api/orders/cart/add/',
                token=token, body={'product_id': product['id'], 'quantity': 1})
        return request('POST', '/api/orders/checkout/', token=token, body={
            'shipping_address': 'E2E Disclosure Address',
            'shipping_city': 'kathmandu',
            'phone': '9800000000',
            'payment_method': payment_method,
            'notes': ORDER_MARKER,
        })

    # --- the mocked path ---
    mocked_method = next((m for m in mocked_values), None)
    if mocked_method is None:
        skip('mocked-payment order', 'no method is currently marked as mocked')
        order = None
    else:
        status, order = place(mocked_method)
        check(f'a {mocked_method} order is accepted', status == 201,
            f'status={status} body={str(order)[:200]}')
        if status == 201:
            check(f'the {mocked_method} order is flagged as simulated',
                order.get('payment_is_mocked') is True,
                f"payment_is_mocked={order.get('payment_is_mocked')}")
            # The flag must not depend on the status being something unusual — the
            # demo deliberately still confirms the order so the flow stays usable.
            check('the order is still usable (it was confirmed, not left pending)',
                order.get('status') == 'confirmed',
                f"status={order.get('status')} — the demo shortcut is to confirm")

    section('The order history does not read as a real payment')

    if order:
        check('the order records which method was used',
            order.get('payment_method') == mocked_method,
            f"payment_method={order.get('payment_method')}")
        check('the display name is the gateway, for the customer to read',
            bool(order.get('payment_method_display')),
            f"display={order.get('payment_method_display')!r}")

        # The timeline is the part a person reads later. `OrderStatusEvent` is the
        # audit trail; if it says "Payment received" then the disclosure above is
        # cosmetic.
        steps = order.get('timeline', {}).get('steps', [])
        labelled = [s for s in steps if s.get('state') in ('done', 'current')]
        check('the timeline shows the order was placed and confirmed',
            len(labelled) >= 2, f'steps={[s.get("key") for s in labelled]}')

        # The order detail endpoint is authenticated (`IsAuthenticated`), so the token
        # has to be passed. Omitting it here returned 401 and the whole block below was
        # silently skipped — the checks simply never ran and never reported a SKIP
        # either, which is the failure mode this project keeps having to relearn.
        # Assert the read worked, rather than guarding on it, so a future regression in
        # the endpoint fails loudly instead of quietly deleting three checks.
        detail_status, detail = request('GET', f'/api/orders/{order["id"]}/', token=token)
        check('the order detail is readable by its owner', detail_status == 200,
            f'status={detail_status} body={str(detail)[:160]}')

        if detail_status == 200:
            # The serializer does not expose raw event notes, so read them from the
            # database — the note is what the admin timeline renders.
            try:
                from orders.models import OrderStatusEvent
                notes = list(
                    OrderStatusEvent.objects
                    .filter(order_id=order['id'], to_status='confirmed')
                    .values_list('note', flat=True)
                )
                check('a confirmed event was recorded', bool(notes), 'no confirmed event')
                joined = ' '.join(notes).lower()
                if MOCKED.get(mocked_method):
                    check('the history says the payment was simulated',
                        'simulated' in joined, f'notes={notes}')
                    check('and says no money was taken',
                        'no money' in joined, f'notes={notes}')
                else:
                    check('a real payment is not described as simulated',
                        'simulated' not in joined, f'notes={notes}')
            except Exception as exc:  # noqa: BLE001
                skip('status-history note', f'could not read events: {exc}')

    section('A genuinely collected method is NOT labelled — the other direction')

    # This is the half that is easy to get wrong. If everything carries the label the
    # label means nothing, and a future reader learns to ignore it.
    real_method = next((m for m in real_values), None)
    if real_method is None:
        skip('non-mocked payment', 'every method is currently marked as mocked')
    else:
        status, cod = place(real_method)
        check(f'a {real_method} order is accepted', status == 201, f'status={status}')
        if status == 201:
            check(f'the {real_method} order is NOT flagged as simulated',
                cod.get('payment_is_mocked') is False,
                f"payment_is_mocked={cod.get('payment_is_mocked')} — "
                f"{real_method} is genuinely collected on delivery")

    section('The flag is derived, never taken from the client')

    request('POST', '/api/orders/cart/add/',
            token=token, body={'product_id': product['id'], 'quantity': 1})
    forged_method = mocked_method or 'esewa'
    status, forged = request('POST', '/api/orders/checkout/', token=token, body={
        'shipping_address': 'E2E Disclosure Address',
        'shipping_city': 'kathmandu',
        'phone': '9800000000',
        'payment_method': forged_method,
        'payment_is_mocked': False,   # a client trying to talk its way out of the label
        'payment_status': 'paid',
        'notes': ORDER_MARKER,
    })
    check('an order can be placed while sending forged flags', status == 201,
        f'status={status}')
    if status == 201:
        check('the server ignores a client-supplied payment_is_mocked',
            forged.get('payment_is_mocked') is True,
            f'the client sent False and got {forged.get("payment_is_mocked")}')

    print(f'\n{"=" * 60}')
    print(f'  {PASS} passed, {FAIL} failed' + (f', {SKIP} skipped' if SKIP else ''))
    if FAILURES:
        print('  Failed checks:')
        for name in FAILURES:
            print(f'    - {name}')
    print(f'{"=" * 60}')
    print('\n  Orders were placed. Clean them up with:')
    print('    ./venv/Scripts/python.exe manage.py purge_verification_orders')
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
