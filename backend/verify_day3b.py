"""Day 3 (remainder) verification — order tracking, dynamic areas, four-state.

Focuses on the customer-facing flow that Day 3's second half touched:

* the order status timeline exposed by the serializer,
* delivery areas served from the database rather than hardcoded,
* a per-area delivery-fee override actually changing what is charged,
* the whole E2E path: add to cart -> checkout -> order history -> timeline.

Restores all mutated data before exiting (stock, areas, cart).

Usage:  python verify_day3b.py      (server must be running on :8000)
"""

import json
import sys
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8000/api'
passed = 0
failed = 0


def check(label, condition, detail=''):
    global passed, failed
    if condition:
        passed += 1
        print(f'  PASS  {label}')
    else:
        failed += 1
        print(f'  FAIL  {label}' + (f'  -> {detail}' if detail else ''))


def request(method, path, body=None, token=None):
    url = f'{BASE}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return e.code, raw
    except urllib.error.URLError as e:
        print(f'\nFATAL: cannot reach {url}: {e}')
        sys.exit(2)


def rows(payload):
    if isinstance(payload, dict) and 'results' in payload:
        return payload['results']
    return payload if isinstance(payload, list) else []


def main():
    print('=' * 68)
    print('DAY 3b VERIFICATION — tracking, dynamic areas, E2E order')
    print('=' * 68)

    admin_tok = login('admin', 'admin123')
    cust_tok = login('testuser', 'test1234')
    if not admin_tok or not cust_tok:
        print('\nFATAL: could not authenticate. Run seed_data first.')
        sys.exit(2)

    # ------------------------------------------------------- dynamic areas
    print('\n[1] Delivery areas come from the database')
    st, cfg = request('GET', '/orders/config/')
    check('store config is 200', st == 200, f'got {st}')
    check('config exposes areas', isinstance(cfg, dict) and len(cfg.get('areas', [])) == 3,
          f"got {len(cfg.get('areas', [])) if isinstance(cfg, dict) else 'n/a'}")
    check('config exposes a default delivery fee',
          isinstance(cfg, dict) and cfg.get('delivery_fee') is not None)

    st, public_areas = request('GET', '/products/areas/')
    check('public area endpoint is 200', st == 200, f'got {st}')
    seeds = {a['slug'] for a in rows(public_areas)}
    check('three valley areas seeded',
          seeds == {'kathmandu', 'lalitpur', 'bhaktapur'}, f'slugs={seeds}')

    # ------------------------------------------- area CRUD affects checkout
    print('\n[2] A new area is immediately usable (the "decorative model" test)')
    st, new_area = request(
        'POST', '/products/admin/areas/',
        {'name': 'Kirtipur', 'district': 'Kathmandu', 'is_active': True},
        token=admin_tok,
    )
    check('admin can add an area', st in (200, 201), f'got {st} {new_area}')
    area_id = new_area.get('id') if isinstance(new_area, dict) else None
    area_slug = new_area.get('slug') if isinstance(new_area, dict) else None

    if area_id:
        # It must appear in the public list straight away — no deploy, no restart.
        st, public_areas = request('GET', '/products/areas/')
        slugs = {a['slug'] for a in rows(public_areas)}
        check('new area appears in the public list immediately',
              area_slug in slugs, f'slug={area_slug} slugs={slugs}')

        # And it must be accepted by checkout validation. Before this fix the
        # serializer used a hardcoded ChoiceField and rejected it.
        st, cfg2 = request('GET', '/orders/config/')
        cfg_slugs = {a['slug'] for a in cfg2.get('areas', [])} if isinstance(cfg2, dict) else set()
        check('new area appears in store config', area_slug in cfg_slugs,
              f'slug={area_slug} cfg={cfg_slugs}')

        # Give it a fee override and confirm the override is honoured.
        st, _ = request(
            'PATCH', f'/products/admin/areas/{area_id}/',
            {'delivery_fee': '250.00'}, token=admin_tok,
        )
        check('admin can set a per-area fee override', st == 200, f'got {st}')

        st, cfg3 = request('GET', '/orders/config/')
        entry = next(
            (a for a in cfg3.get('areas', []) if a['slug'] == area_slug), None
        ) if isinstance(cfg3, dict) else None
        check('override is reflected in store config',
              entry and float(entry['delivery_fee']) == 250.0 and entry['is_override'] is True,
              f'got {entry}')

    # ------------------------------------------------------- E2E order
    print('\n[3] End-to-end: add to cart -> checkout -> history -> timeline')
    request('DELETE', '/orders/cart/', token=cust_tok)  # no-op guard; cart is per-line

    # Clear any existing cart lines.
    st, cart = request('GET', '/orders/cart/', token=cust_tok)
    for line in rows(cart.get('items', []) if isinstance(cart, dict) else []):
        request('DELETE', f'/orders/cart/remove/{line["id"]}/', token=cust_tok)

    st, products = request('GET', '/products/?ordering=-popularity_score')
    product = rows(products)[0] if rows(products) else None
    check('a product is available to order', product is not None)

    if not product:
        return report()

    original_stock = product['stock']
    check('chosen product has stock', original_stock > 0, f'stock={original_stock}')

    st, _ = request(
        'POST', '/orders/cart/add/',
        {'product_id': product['id'], 'quantity': 1}, token=cust_tok,
    )
    check('add to cart is 200', st == 200, f'got {st}')

    st, cart = request('GET', '/orders/cart/', token=cust_tok)
    check('cart now has one line',
          isinstance(cart, dict) and len(cart.get('items', [])) == 1,
          f"got {len(cart.get('items', [])) if isinstance(cart, dict) else 'n/a'}")

    # Checkout into the OVERRIDDEN area so the fee override is exercised.
    target_slug = area_slug or 'kathmandu'
    expected_fee = 250.0 if area_slug else 100.0

    st, order = request(
        'POST', '/orders/checkout/',
        {
            'shipping_address': 'Day3b Verification Road',
            'shipping_city': target_slug,
            'phone': '9800000000',
            'payment_method': 'cod',
            'notes': 'created by verify_day3b.py',
        },
        token=cust_tok,
    )
    check('checkout succeeds', st in (200, 201), f'got {st} {order}')
    order_id = order.get('id') if isinstance(order, dict) else None

    if order_id:
        # --- delivery fee is real, and the override applied
        st, detail = request('GET', f'/orders/{order_id}/', token=cust_tok)
        check('order detail is 200', st == 200, f'got {st}')
        if st == 200:
            fee = float(detail['delivery_fee'])
            subtotal = float(detail['subtotal'])
            total = float(detail['total_amount'])
            check(f'area override applied (fee={expected_fee})',
                  fee == expected_fee, f'got {fee}')
            check('total == subtotal + fee',
                  abs(total - (subtotal + fee)) < 0.01,
                  f'{total} != {subtotal} + {fee}')
            check('shipping_city stores the area slug',
                  detail['shipping_city'] == target_slug,
                  f"got {detail['shipping_city']}")
            check('item count is 1', len(detail['items']) == 1,
                  f"got {len(detail['items'])}")

            # --- the timeline (the new feature)
            tl = detail.get('timeline')
            check('order exposes a timeline', isinstance(tl, dict), f'got {type(tl).__name__}')
            if isinstance(tl, dict):
                steps = tl.get('steps', [])
                check('timeline has 5 steps for a live order', len(steps) == 5,
                      f'got {len(steps)}')
                check('timeline starts at Order Placed',
                      steps and steps[0]['label'] == 'Order Placed',
                      f"got {steps[0]['label'] if steps else None}")
                check('timeline reports the current status',
                      tl.get('current') == 'pending', f"got {tl.get('current')}")
                check('exactly one step is current',
                      sum(1 for s in steps if s['state'] == 'current') == 1,
                      f"states={[s['state'] for s in steps]}")
                check('first step is current, rest upcoming',
                      steps[0]['state'] == 'current'
                      and all(s['state'] == 'upcoming' for s in steps[1:]),
                      f"states={[s['state'] for s in steps]}")
                check('order is not terminal', tl.get('is_terminal') is False)

        # --- stock decremented
        st, after = request('GET', f'/products/{product["slug"]}/')
        if st == 200:
            check('stock decremented by 1',
                  after['stock'] == original_stock - 1,
                  f'{original_stock} -> {after["stock"]}')

        # --- cart cleared
        st, cart = request('GET', '/orders/cart/', token=cust_tok)
        check('cart is empty after checkout',
              isinstance(cart, dict) and len(cart.get('items', [])) == 0,
              f"got {len(cart.get('items', [])) if isinstance(cart, dict) else 'n/a'}")

        # --- appears in history
        st, history = request('GET', '/orders/', token=cust_tok)
        check('order history is 200', st == 200, f'got {st}')
        ids = {o['id'] for o in rows(history)}
        check('new order appears in history', order_id in ids, f'ids={sorted(ids)}')

        # --- timeline transitions when the admin advances the status
        st, _ = request(
            'PATCH', f'/orders/admin/orders/{order_id}/',
            {'status': 'confirmed'}, token=admin_tok,
        )
        check('admin can advance the order status', st == 200, f'got {st}')

        st, detail = request('GET', f'/orders/{order_id}/', token=cust_tok)
        tl = detail.get('timeline', {}) if st == 200 else {}
        steps = tl.get('steps', [])
        check('timeline advanced to current=confirmed',
              tl.get('current') == 'confirmed', f"got {tl.get('current')}")
        check('step 0 is done and step 1 is current',
              len(steps) > 1 and steps[0]['state'] == 'done'
              and steps[1]['state'] == 'current',
              f"states={[s['state'] for s in steps]}")

        # --- delivered is terminal
        request('PATCH', f'/orders/admin/orders/{order_id}/',
                {'status': 'delivered'}, token=admin_tok)
        st, detail = request('GET', f'/orders/{order_id}/', token=cust_tok)
        tl = detail.get('timeline', {}) if st == 200 else {}
        check('delivered is terminal', tl.get('is_terminal') is True,
              f"got {tl.get('is_terminal')}")
        check('all steps done when delivered',
              all(s['state'] == 'done' for s in tl.get('steps', [])),
              f"states={[s['state'] for s in tl.get('steps', [])]}")

        # --- cancelled is a distinct 2-step timeline
        request('PATCH', f'/orders/admin/orders/{order_id}/',
                {'status': 'cancelled'}, token=admin_tok)
        st, detail = request('GET', f'/orders/{order_id}/', token=cust_tok)
        tl = detail.get('timeline', {}) if st == 200 else {}
        steps = tl.get('steps', [])
        check('cancelled timeline has 2 steps', len(steps) == 2, f'got {len(steps)}')
        check('cancelled step is marked cancelled',
              any(s['state'] == 'cancelled' for s in steps),
              f"states={[s['state'] for s in steps]}")

        # --- another customer cannot read this order
        other_tok = login('vendor1', 'vendor1234')
        if other_tok:
            st, _ = request('GET', f'/orders/{order_id}/', token=other_tok)
            check('a different user cannot read this order (404)', st == 404, f'got {st}')

    # ------------------------------------------------- cleanup
    print('\n[4] Cleanup — restore the database to its seeded state')
    if area_id:
        st, _ = request('DELETE', f'/products/admin/areas/{area_id}/', token=admin_tok)
        check('temporary area removed', st == 204, f'got {st}')

    if order_id:
        # The only mutation this suite makes to a seeded product is the stock
        # decrement from checkout, so restoring the stock is the correct undo.
        # (An earlier version also deleted the product here, which then made the
        #  restore PATCH 404 — the product was already gone.)
        st, _ = request(
            'PATCH', f'/products/admin/products/{product["id"]}/',
            {'stock': original_stock}, token=admin_tok,
        )
        check('product stock restored', st == 200, f'got {st}')

    return report()


def login(username, password):
    st, body = request('POST', '/auth/login/', {'username': username, 'password': password})
    return body.get('access') if st == 200 else None


def report():
    print('\n' + '=' * 68)
    total = passed + failed
    print(f'RESULT: {passed}/{total} checks passed')
    if failed:
        print(f'        {failed} FAILED')
    print('=' * 68)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
