"""Day 3 live end-to-end verification.

Runs against the real dev server on :8000 and exercises the write paths the
admin dashboard now depends on: product CRUD, category CRUD, area CRUD, vendor
scoping, and role enforcement.

Every request goes through the JWT API — there is no session auth — so the
absence of a bearer token is itself one of the assertions.

Usage:  python verify_day3.py
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
    """Returns (status, parsed_body). Never raises on HTTP error status."""
    url = f'{BASE}{path}'
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
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


def login(username, password):
    status, body = request(
        'POST', '/auth/login/', {'username': username, 'password': password}
    )
    if status != 200:
        return None
    return body.get('access')


def rows(payload):
    """Unwrap a DRF paginated response into its list of rows.

    The default pagination class returns {count, next, previous, results}; a
    naive ``len(payload)`` yields 4 (the number of keys) rather than the number
    of records, which silently makes cross-scope comparisons meaningless.
    """
    if isinstance(payload, dict) and 'results' in payload:
        return payload['results']
    if isinstance(payload, list):
        return payload
    return []


def count_all(path, token):
    """Total record count across every page, following ``next`` links."""
    total = 0
    seen = 0
    status, payload = request('GET', path, token=token)
    while True:
        rows_here = rows(payload)
        total += len(rows_here)
        if not isinstance(payload, dict) or not payload.get('next'):
            break
        # ``next`` is an absolute URL; strip the base so request() can rebuild it.
        nxt = payload['next']
        path = nxt[len(BASE):] if nxt.startswith(BASE) else nxt
        status, payload = request('GET', path, token=token)
        seen += 1
        if seen > 20:  # safety stop
            break
    return total


def main():
    print('=' * 68)
    print('DAY 3 VERIFICATION — roles, vendor scoping, admin CRUD')
    print('=' * 68)

    # ---------------------------------------------------------------- auth
    print('\n[1] Authentication')
    admin_tok = login('admin', 'admin123')
    check('admin can log in', admin_tok is not None)
    if not admin_tok:
        print('\nCannot continue without an admin token.')
        sys.exit(2)

    vendor_tok = login('vendor1', 'vendor1234')
    check('vendor1 can log in', vendor_tok is not None)

    cust_tok = login('testuser', 'test1234')
    check('testuser can log in', cust_tok is not None)

    anon_status, _ = request('GET', '/products/admin/products/')
    check('anonymous admin-list request is 401', anon_status == 401, f'got {anon_status}')

    # ------------------------------------------------------------- profile
    print('\n[2] Role resolution as seen by the API')
    st, prof = request('GET', '/auth/profile/', token=admin_tok)
    check('admin profile is 200', st == 200, f'got {st}')
    if st == 200:
        p_admin = prof.get('profile') or {}
        check('admin reports is_admin_user', p_admin.get('is_admin_user') is True)
        check('admin profile exposes role', p_admin.get('role') == 'super_admin',
              f"role={p_admin.get('role')}")

    st, prof_v = request('GET', '/auth/profile/', token=vendor_tok)
    check('vendor profile is 200', st == 200, f'got {st}')
    if st == 200:
        p_v = prof_v.get('profile') or {}
        check('vendor role is vendor', p_v.get('role') == 'vendor',
              f"role={p_v.get('role')}")

    # --------------------------------------------------------------- areas
    print('\n[3] Delivery areas')
    st, areas = request('GET', '/products/areas/')
    check('public area list is 200', st == 200, f'got {st}')
    area_rows = rows(areas)
    slugs = {a['slug'] for a in area_rows}
    check('seeded valley areas present',
          {'kathmandu', 'lalitpur', 'bhaktapur'} <= slugs, f'slugs={slugs}')

    st, _ = request('GET', '/products/admin/areas/', token=cust_tok)
    check('customer cannot list admin areas (403)', st == 403, f'got {st}')

    st, _ = request('GET', '/products/admin/areas/', token=admin_tok)
    check('admin can list admin areas (200)', st == 200, f'got {st}')

    # ------------------------------------------------------- area CRUD
    st, created_area = request(
        'POST', '/products/admin/areas/',
        {'name': 'Verification Zone', 'district': 'Kathmandu', 'is_active': True},
        token=admin_tok,
    )
    check('admin can create an area', st in (200, 201), f'got {st} {created_area}')
    area_id = created_area.get('id') if isinstance(created_area, dict) else None

    if area_id:
        st, _ = request(
            'PATCH', f'/products/admin/areas/{area_id}/',
            {'delivery_fee': '150.00'}, token=admin_tok,
        )
        check('admin can patch an area fee', st == 200, f'got {st}')

        st, _ = request('DELETE', f'/products/admin/areas/{area_id}/', token=admin_tok)
        check('admin can delete the area', st == 204, f'got {st}')

    # --------------------------------------------------------- vendor list
    print('\n[4] Vendor scoping')
    st, vendors_payload = request('GET', '/products/admin/vendors/', token=admin_tok)
    vendors = rows(vendors_payload)
    check('admin can list vendors', st == 200, f'got {st}')
    vendor_id = vendors[0]['id'] if vendors else None
    check('at least one vendor exists', vendor_id is not None)

    st, v_vendors_payload = request('GET', '/products/admin/vendors/', token=vendor_tok)
    v_vendors = rows(v_vendors_payload)
    check('vendor can list vendors (scoped)', st == 200, f'got {st}')
    check('vendor sees exactly one vendor record (itself)',
          len(v_vendors) == 1, f'got {len(v_vendors)}')

    st, _ = request('GET', '/products/admin/vendors/', token=cust_tok)
    check('customer cannot list vendors (403)', st == 403, f'got {st}')

    st, _ = request(
        'GET', f'/products/admin/vendors/{vendor_id + 999}/', token=admin_tok
    )
    check('missing vendor detail is 404', st == 404, f'got {st}')

    # ------------------------------------------------- admin products view
    print('\n[5] Product catalogue access')
    admin_count = count_all('/products/admin/products/', admin_tok)
    check('admin sees all products', admin_count == 35, f'got {admin_count}')

    vendor_count = count_all('/products/admin/products/', vendor_tok)
    check('vendor can list own products', vendor_count == 12, f'got {vendor_count}')
    check('vendor sees a strict subset of the catalogue',
          vendor_count < admin_count,
          f'vendor={vendor_count} admin={admin_count}')

    st, _ = request('GET', '/products/admin/products/', token=cust_tok)
    check('customer cannot list admin products (403)', st == 403, f'got {st}')

    # Filtering by another vendor must not become an enumeration oracle.
    other_id = next((v['id'] for v in vendors if v['id'] != vendor_id), None)
    if other_id:
        st, probe = request(
            'GET', f'/products/admin/products/?vendor={other_id}', token=vendor_tok
        )
        check('vendor cannot probe another vendor via ?vendor=',
              st == 200 and rows(probe) == [],
              f'got {st} {len(rows(probe))} rows')

        # And the vendor's own filter still works.
        st, mine = request(
            'GET', f'/products/admin/products/?vendor={vendor_id}', token=vendor_tok
        )
        check('vendor can filter by their own id',
              st == 200 and len(rows(mine)) > 0, f'got {st}')

    # --------------------------------------------------- product CRUD
    print('\n[6] Product write path')
    st, cats = request('GET', '/products/admin/categories/', token=admin_tok)
    check('admin can list categories', st == 200 and len(cats) > 0, f'got {st}')
    cat_id = cats[0]['id'] if st == 200 and cats else None

    if cat_id:
        st, new_product = request(
            'POST', '/products/admin/products/',
            {
                'name': 'Day3 Verification Item',
                'description': 'created by verify_day3.py',
                'price': '42.00',
                'stock': 7,
                'category': cat_id,
                'unit': 'packet',
                'is_active': True,
            },
            token=admin_tok,
        )
        check('admin can create a product', st in (200, 201), f'got {st} {new_product}')
        pid = new_product.get('id') if isinstance(new_product, dict) else None
        check('created product returns an id', pid is not None)

        if pid:
            st, fetched = request(
                'GET', f'/products/admin/products/{pid}/', token=admin_tok
            )
            check('created product is retrievable', st == 200, f'got {st}')
            check('price round-trips', fetched and str(fetched.get('price')) == '42.00',
                  f"got {fetched.get('price') if fetched else None}")

            st, _ = request(
                'PATCH', f'/products/admin/products/{pid}/',
                {'price': '55.50', 'stock': 21}, token=admin_tok,
            )
            check('admin can patch a product', st == 200, f'got {st}')

            st, refetched = request(
                'GET', f'/products/admin/products/{pid}/', token=admin_tok
            )
            check('patch persisted', refetched and str(refetched.get('price')) == '55.50',
                  f"got {refetched.get('price') if refetched else None}")

            st, _ = request(
                'POST', '/products/admin/products/',
                {'name': '', 'description': 'x', 'price': '1.00',
                 'stock': 1, 'category': cat_id},
                token=admin_tok,
            )
            check('empty name is rejected (400)', st == 400, f'got {st}')

            st, _ = request(
                'DELETE', f'/products/admin/products/{pid}/', token=admin_tok
            )
            check('admin can delete the product', st == 204, f'got {st}')

            st, _ = request(
                'GET', f'/products/admin/products/{pid}/', token=admin_tok
            )
            check('deleted product is gone (404)', st == 404, f'got {st}')

    # --------------------------------------------------- escalation
    print('\n[7] Privilege escalation guards')
    st, me = request('GET', '/auth/profile/', token=cust_tok)
    check('customer profile loads', st == 200, f'got {st}')

    st, _ = request(
        'PATCH', '/auth/profile/', {'role': 'super_admin'}, token=cust_tok
    )
    st2, after = request('GET', '/auth/profile/', token=cust_tok)
    p_after = after.get('profile') or {}
    check('customer role did not change',
          p_after.get('role') == 'customer', f"role={p_after.get('role')}")
    check('customer is not is_admin_user', p_after.get('is_admin_user') is not True)

    st, _ = request(
        'POST', '/products/admin/products/',
        {'name': 'Escalated', 'description': 'x', 'price': '1.00',
         'stock': 1, 'category': cat_id},
        token=cust_tok,
    )
    check('customer cannot create a product (403)', st == 403, f'got {st}')

    st, _ = request('POST', '/products/admin/vendors/',
                    {'user': 1, 'shop_name': 'Rogue'}, token=cust_tok)
    check('customer cannot create a vendor (403)', st == 403, f'got {st}')

    # --------------------------------------------------- analytics scope
    print('\n[8] Analytics scoping')
    st, admin_ov = request('GET', '/analytics/sales/', token=admin_tok)
    check('admin analytics is 200', st == 200, f'got {st}')
    check('admin scope is "all"', admin_ov and admin_ov.get('scope') == 'all',
          f"scope={admin_ov.get('scope') if admin_ov else None}")

    st, vendor_ov = request('GET', '/analytics/sales/', token=vendor_tok)
    check('vendor analytics is 200', st == 200, f'got {st}')
    check('vendor scope is "vendor"', vendor_ov and vendor_ov.get('scope') == 'vendor',
          f"scope={vendor_ov.get('scope') if vendor_ov else None}")
    if admin_ov and vendor_ov:
        check('vendor sees fewer products than admin',
              vendor_ov['total_products'] < admin_ov['total_products'],
              f"vendor={vendor_ov['total_products']} admin={admin_ov['total_products']}")

    st, _ = request('GET', '/analytics/sales/', token=cust_tok)
    check('customer analytics is 403', st == 403, f'got {st}')

    st, _ = request('GET', '/analytics/inventory/', token=vendor_tok)
    check('vendor inventory is 200', st == 200, f'got {st}')

    st, _ = request('GET', '/analytics/demand-forecast/', token=vendor_tok)
    check('vendor can read demand forecast', st == 200, f'got {st}')

    # ------------------------------------------------------ storefront
    print('\n[9] Storefront is unaffected by scoping')
    st, public_products = request('GET', '/products/')
    check('public product list is 200', st == 200, f'got {st}')
    check('public list still paginates', isinstance(public_products, dict)
          and 'count' in public_products, f'type={type(public_products).__name__}')
    check('public catalogue exposes every product',
          isinstance(public_products, dict)
          and public_products.get('count') == 35,
          f"count={public_products.get('count') if isinstance(public_products, dict) else None}")

    st, site_cfg = request('GET', '/orders/config/')
    check('store config is public', st == 200, f'got {st}')
    check('delivery fee is present', site_cfg and 'delivery_fee' in site_cfg,
          f'got {site_cfg}')

    st, public_cats = request('GET', '/products/categories/')
    check('public category list is 200', st == 200, f'got {st}')

    # ------------------------------------------------------------ summary
    print('\n' + '=' * 68)
    total = passed + failed
    print(f'RESULT: {passed}/{total} checks passed')
    if failed:
        print(f'        {failed} FAILED')
    print('=' * 68)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
