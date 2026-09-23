"""Day 8 — ritual and kit authoring, over the real HTTP API.

`docs/CURRENT-STATE.md` recorded the Day 8 theme as: *the dashboard can show the
puja domain but cannot edit it.* `/festivals` made no write calls at all, and
`/pujas` did not exist. The backend write endpoints were added first; this proves
they behave, and that the storefront sees what they write.

The checks worth having are the ones a happy-path smoke test would miss:

* the item lists must come back **unpaginated** — Bratabandha has 14 items and
  Daily Puja has 21, and the project-wide PAGE_SIZE is 12, so a paginated list
  would silently show an incomplete kit and look fine;
* a repeated ritual name must **uniquify the slug**, not raise a 500;
* a customer must still be refused, and a vendor must still be read-only — the
  new endpoints must not be looser than the kit ones they mirror.

Everything this script creates is deleted again, so the seeded demo data is
untouched. Run against a live server:

    ./venv/Scripts/python.exe manage.py runserver
    ./venv/Scripts/python.exe verify_day8.py

Usage:  ./venv/Scripts/python.exe verify_day8.py
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

# Unique per run so a re-run cannot collide with its own leftovers.
RUN = uuid.uuid4().hex[:8]
KIT_NAME = f'VerifyDay8 Kit {RUN}'
PUJA_NAME = f'VerifyDay8 Ritual {RUN}'


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


def request(method, path, token=None, body=None, timeout=30):
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
    if status != 200 or not isinstance(body, dict):
        return None
    return body.get('access')


def as_list(body):
    """Item endpoints are unpaginated, so `body` should be a bare list.

    Deliberately strict: a `results` dict would still pass a `len()` check
    against a page and hide exactly the bug this is looking for.
    """
    return body if isinstance(body, list) else None


def fetch_products(admin, want):
    """Walk the admin product pages until `want` products are collected.

    The product list is paginated at PAGE_SIZE = 12, so taking the first response
    yields 12 rows however many exist — and a kit built from those 12 can never
    cross the 12-row pagination boundary the item list is being tested against.
    (This bit the first version of this script: it reported 11 failures that were
    all the same verifier bug.)
    """
    out, page = [], 1
    while len(out) < want and page <= 10:
        status, body = request('GET', f'/api/products/admin/products/?page={page}', admin)
        if status != 200:
            break
        if isinstance(body, dict):
            out.extend(body.get('results') or [])
            if not body.get('next'):
                break
        else:
            out.extend(body or [])
            break
        page += 1
    return out


# ---------------------------------------------------------------- vocabulary

def test_choices():
    section('The festival vocabulary the forms draw on')

    status, body = request('GET', '/api/festivals/choices/')
    check('choices endpoint is public', status == 200, f'status={status}')
    if status != 200:
        return
    check('it returns a list of {value, label}',
          isinstance(body, list) and body and set(body[0]) == {'value', 'label'},
          f'body={body[:2] if isinstance(body, list) else body}')
    values = [row['value'] for row in body]
    check('it carries the whole enum, not just the types in use',
          'nag_panchami' in values and 'other' in values, f'values={values}')


# ---------------------------------------------------------------- authz

def test_dashboard_payload_contract(admin):
    """Every field the dashboard table renders must exist on every row.

    `DomainManager`'s column renderers read these keys directly — `puja.kit_names.join()`,
    `kit.item_count`, and so on. A missing key is not a validation error, it is a
    render-time TypeError, and the admin build would not catch it: the data is fetched
    at runtime, so a page whose payload lost a field compiles cleanly and then dies in
    the browser. This is the cheap half of that check.

    (A real browser pass would also cover it. It is not run here — the project has no
    browser automation installed and setting it up is a ~500 MB Chromium download. The
    API half of the contract is the part that can silently drift, so it is pinned.)
    """
    section('The payload the dashboard actually renders')

    kit_fields = {'id', 'name', 'festival_type', 'description', 'discount_percent',
                  'puja', 'is_active', 'item_count'}
    puja_fields = {'id', 'name', 'slug', 'description', 'occasion_type', 'is_active',
                   'item_count', 'kit_count', 'kit_names'}

    for path, required, label in [
        ('/api/festivals/admin/kits/', kit_fields, 'kit'),
        ('/api/festivals/admin/pujas/', puja_fields, 'ritual'),
    ]:
        status, rows = request('GET', path, admin)
        check(f'the {label} list loads', status == 200, f'status={status}')
        if status != 200 or not rows:
            check(f'at least one {label} row exists to check', bool(rows))
            continue

        missing = {key for key in required if any(key not in row for row in rows)}
        check(f'every {label} row carries every field the table reads',
              not missing, f'missing={sorted(missing)}')

        if label == 'kit':
            check('item_count is an integer, not a string',
                  all(isinstance(row['item_count'], int) for row in rows),
                  f'sample={rows[0]["item_count"]!r}')
            check('puja is null or an id',
                  all(row['puja'] is None or isinstance(row['puja'], int) for row in rows),
                  f'sample={rows[0]["puja"]!r}')
        else:
            check('kit_names is always a list, so .join() cannot throw',
                  all(isinstance(row['kit_names'], list) for row in rows),
                  f'sample={rows[0]["kit_names"]!r}')
            check('kit_count agrees with the length of kit_names',
                  all(row['kit_count'] == len(row['kit_names']) for row in rows),
                  f'sample={rows[0]["kit_count"]}/{len(rows[0]["kit_names"])}')
            check('the slug is present, for the "/pujas/<slug>" hint in the table',
                  all(row.get('slug') for row in rows))


def test_authorization(admin, vendor, customer):
    section('Authorization not weakened')

    for path in ['/api/festivals/admin/kits/', '/api/festivals/admin/pujas/']:
        status, _ = request('GET', path, admin)
        check(f'admin 200 on {path}', status == 200, f'status={status}')
        status, _ = request('GET', path)
        check(f'anonymous 401 on {path}', status == 401, f'status={status}')
        status, _ = request('GET', path, customer)
        check(f'customer 403 on {path}', status == 403, f'status={status}')

    # A vendor may read a kit and a ritual, but must not write either.
    status, _ = request('GET', '/api/festivals/admin/pujas/', vendor)
    check('vendor may read rituals', status == 200, f'status={status}')

    for path, payload in [
        ('/api/festivals/admin/kits/', {'name': 'Nope', 'festival_type': 'dashain',
                                        'description': 'x'}),
        ('/api/festivals/admin/pujas/', {'name': 'Nope'}),
    ]:
        status, _ = request('POST', path, vendor, payload)
        check(f'vendor 403 writing {path}', status == 403, f'status={status}')
        status, _ = request('POST', path, customer, payload)
        check(f'customer 403 writing {path}', status == 403, f'status={status}')


# ---------------------------------------------------------------- kit CRUD

def test_kit_authoring(admin, products):
    section('A kit can be created, filled, edited and deleted')

    status, kit = request('POST', '/api/festivals/admin/kits/', admin, {
        'name': KIT_NAME,
        'festival_type': 'dashain',
        'description': 'Created by verify_day8.',
        'discount_percent': 10,
        'puja': None,
        'is_active': True,
    })
    check('kit created', status == 201, f'status={status} body={kit}')
    if status != 201:
        return None

    kit_id = kit['id']
    check('a new kit starts with no items', kit.get('item_count') == 0, f'kit={kit}')
    # Inverted on Day 13, deliberately. This check used to read
    # `'image' not in kit`, because a JSON form cannot set a file field and the field
    # was therefore left out of the write payload entirely. The dashboard now uploads
    # multipart, so the field is included and the original guarantee no longer holds.
    # Asserting the *new* contract rather than deleting the check keeps the change
    # visible: the old promise is gone, and this says so.
    check('the image field is part of the payload (reversed on Day 13)',
          'image' in kit, f'kit keys={sorted(kit.keys())}')

    status, body = request('GET', '/api/festivals/admin/kits/', admin)
    check('it appears in the admin list',
          any(row['id'] == kit_id for row in body), f'status={status}')

    # --- fill it -------------------------------------------------------
    status, body = request('GET', f'/api/festivals/admin/kits/{kit_id}/items/', admin)
    check('the item list is a bare list', as_list(body) is not None, f'body={body}')
    check('a new kit has zero items', body == [], f'body={body}')

    added = 0
    for product in products[:14]:
        status, _ = request('POST', f'/api/festivals/admin/kits/{kit_id}/items/', admin, {
            'kit': kit_id, 'product': product['id'], 'quantity': 1, 'is_required': True,
        })
        if status == 201:
            added += 1
    check('14 items can be added', added == 14, f'added={added}')

    status, body = request('GET', f'/api/festivals/admin/kits/{kit_id}/items/', admin)
    rows = as_list(body)
    check('the item list is still a bare list', rows is not None, f'body={body}')
    check('the unpaginated list returns all 14 (PAGE_SIZE is 12)',
          rows is not None and len(rows) == 14, f'len={len(rows) if rows else None}')

    if rows:
        check('item rows carry the product name for the table',
              bool(rows[0].get('product_name')), f'row={rows[0]}')

    status, kit = request('GET', f'/api/festivals/admin/kits/{kit_id}/', admin)
    check('the kit reports its item count', kit.get('item_count') == 14, f'kit={kit}')

    # --- the duplicate guard -------------------------------------------
    status, _ = request('POST', f'/api/festivals/admin/kits/{kit_id}/items/', admin, {
        'kit': kit_id, 'product': products[0]['id'], 'quantity': 1, 'is_required': True,
    })
    check('the same product cannot be added twice', status == 400, f'status={status}')

    # --- edit an item in place -----------------------------------------
    if rows:
        item_id = rows[0]['id']
        status, body = request('PATCH', f'/api/festivals/admin/kit-items/{item_id}/',
                               admin, {'quantity': 3, 'is_required': False})
        check('an item can be edited, not only deleted and re-added',
              status == 200, f'status={status}')
        check('the new quantity stuck', body.get('quantity') == 3, f'body={body}')
        check('the required flag flipped', body.get('is_required') is False, f'body={body}')

        status, _ = request('DELETE', f'/api/festivals/admin/kit-items/{item_id}/', admin)
        check('an item can be removed', status == 204, f'status={status}')

        status, body = request('GET', f'/api/festivals/admin/kits/{kit_id}/items/', admin)
        check('removing an item leaves 13', len(as_list(body) or []) == 13,
              f'len={len(body) if isinstance(body, list) else body}')

    # --- the storefront sees it ----------------------------------------
    status, body = request('GET', '/api/festivals/kits/')
    public = [k for k in body if k['id'] == kit_id] if isinstance(body, list) else []
    check('the kit is live on the storefront', len(public) == 1, f'status={status}')
    if public:
        check('the storefront kit reports the same item count',
              public[0]['item_count'] == 13, f'kit={public[0]}')

    # --- and can be hidden ---------------------------------------------
    status, _ = request('PATCH', f'/api/festivals/admin/kits/{kit_id}/', admin,
                        {'is_active': False})
    check('a kit can be deactivated', status == 200, f'status={status}')
    status, body = request('GET', '/api/festivals/kits/')
    check('a deactivated kit leaves the storefront',
          not any(k['id'] == kit_id for k in body), 'still listed')

    return kit_id


# ---------------------------------------------------------------- ritual CRUD

def test_ritual_authoring(admin, products, kit_id):
    section('A ritual can be created, filled, linked and deleted')

    status, puja = request('POST', '/api/festivals/admin/pujas/', admin, {
        'name': PUJA_NAME,
        'description': 'Created by verify_day8.',
        'occasion_type': 'other',
        'is_active': True,
    })
    check('ritual created', status == 201, f'status={status} body={puja}')
    if status != 201:
        return None

    puja_id = puja['id']
    check('the slug is derived server-side', bool(puja.get('slug')), f'puja={puja}')
    check('a new ritual reports no kit', puja.get('kit_names') == [], f'puja={puja}')

    # A repeated name must uniquify, not 500.
    status, second = request('POST', '/api/festivals/admin/pujas/', admin, {'name': PUJA_NAME})
    check('a repeated name still creates', status == 201, f'status={status} body={second}')
    if status == 201:
        check('and gets a distinct slug', second['slug'] != puja['slug'],
              f'{second["slug"]} vs {puja["slug"]}')

    # The slug is not client-writable.
    status, body = request('PATCH', f'/api/festivals/admin/pujas/{puja_id}/', admin,
                           {'slug': 'hijacked'})
    check('the slug is read-only', body.get('slug') == puja['slug'], f'body={body}')

    # --- items ---------------------------------------------------------
    status, body = request('GET', f'/api/festivals/admin/pujas/{puja_id}/items/', admin)
    check('the ritual item list is a bare list', as_list(body) is not None, f'body={body}')

    added = 0
    for product in products[:14]:
        status, _ = request('POST', f'/api/festivals/admin/pujas/{puja_id}/items/', admin, {
            'puja': puja_id, 'product': product['id'], 'quantity': 1, 'is_required': True,
        })
        if status == 201:
            added += 1
    check('14 samagri rows can be added', added == 14, f'added={added}')

    status, body = request('GET', f'/api/festivals/admin/pujas/{puja_id}/items/', admin)
    rows = as_list(body)
    check('all 14 come back unpaginated (Daily Puja has 21)',
          rows is not None and len(rows) == 14, f'len={len(rows) if rows else None}')

    status, body = request('GET', f'/api/festivals/admin/pujas/', admin)
    row = next((r for r in body if r['id'] == puja_id), None)
    check('the admin list reports the item count', row and row['item_count'] == 14,
          f'row={row}')

    # --- link a kit, from the kit side ---------------------------------
    if kit_id:
        # `test_kit_authoring` left it deactivated to prove the storefront hides
        # it. Reactivate, because an inactive kit is deliberately *not* offered
        # as a ritual's bundle (`Puja.kit` skips inactive kits).
        request('PATCH', f'/api/festivals/admin/kits/{kit_id}/', admin, {'is_active': True})

        status, _ = request('PATCH', f'/api/festivals/admin/kits/{kit_id}/', admin,
                            {'puja': puja_id})
        check('a kit can declare which ritual it serves', status == 200, f'status={status}')

        status, body = request('GET', '/api/festivals/admin/pujas/', admin)
        row = next((r for r in body if r['id'] == puja_id), None)
        check('the ritual now reports the kit by name',
              row and row['kit_names'] == [KIT_NAME], f'row={row}')
        check('and reports a kit count of 1', row and row['kit_count'] == 1, f'row={row}')

    # --- the storefront sees it ----------------------------------------
    status, detail = request('GET', f'/api/festivals/pujas/{puja["slug"]}/')
    check('the ritual is live on the storefront', status == 200, f'status={status}')
    if status == 200:
        check('its samagri are listed',
              len(detail.get('items', [])) == 14, f'items={len(detail.get("items", []))}')
        check('the linked kit is offered alongside it',
              detail.get('kit') is not None, f'kit={detail.get("kit")}')

    # A deactivated kit must stop being offered, without hiding the ritual.
    if kit_id:
        request('PATCH', f'/api/festivals/admin/kits/{kit_id}/', admin, {'is_active': False})
        status, detail = request('GET', f'/api/festivals/pujas/{puja["slug"]}/')
        check('the ritual still resolves', status == 200, f'status={status}')
        check('but an inactive kit is no longer offered',
              detail.get('kit') is None, f'kit={detail.get("kit")}')
        request('PATCH', f'/api/festivals/admin/kits/{kit_id}/', admin, {'is_active': True})

    # --- and can be hidden ---------------------------------------------
    status, _ = request('PATCH', f'/api/festivals/admin/pujas/{puja_id}/', admin,
                        {'is_active': False})
    check('a ritual can be deactivated', status == 200, f'status={status}')
    status, _ = request('GET', f'/api/festivals/pujas/{puja["slug"]}/')
    check('a deactivated ritual leaves the storefront', status == 404, f'status={status}')

    return puja_id


# ---------------------------------------------------------------- cleanup

def test_cleanup(admin, kit_id, puja_id, second_puja_id):
    section('Cleanup — the seeded demo data is left alone')

    if kit_id:
        status, _ = request('DELETE', f'/api/festivals/admin/kits/{kit_id}/', admin)
        check('the scratch kit is deleted', status == 204, f'status={status}')
    for pid in [puja_id, second_puja_id]:
        if pid:
            status, _ = request('DELETE', f'/api/festivals/admin/pujas/{pid}/', admin)
            check(f'the scratch ritual {pid} is deleted', status == 204, f'status={status}')

    status, body = request('GET', '/api/festivals/kits/')
    check('no scratch kit remains on the storefront',
          not any(k['name'].startswith('VerifyDay8') for k in body), 'leftover found')

    status, body = request('GET', '/api/festivals/pujas/')
    check('no scratch ritual remains on the storefront',
          not any(p['name'].startswith('VerifyDay8') for p in body), 'leftover found')
    check('the seeded rituals are still there', len(body) >= 8, f'count={len(body)}')


def main():
    print(f'Verifying against {BASE}')

    admin = login('admin', 'admin123')
    check('admin can log in', admin is not None)
    if not admin:
        return 1
    vendor = login('vendor1', 'vendor1234')
    customer = login('testuser', 'test1234')
    check('vendor can log in', vendor is not None)
    check('customer can log in', customer is not None)

    # 14 distinct products, so the 12-row pagination boundary is crossed.
    products = fetch_products(admin, 14)
    check('at least 14 products exist to build a kit from',
          len(products) >= 14, f'count={len(products)}')

    test_choices()
    test_dashboard_payload_contract(admin)
    test_authorization(admin, vendor, customer)

    kit_id = test_kit_authoring(admin, products)
    puja_id = test_ritual_authoring(admin, products, kit_id)

    # The second ritual (the duplicate-name one) also needs removing.
    status, body = request('GET', '/api/festivals/admin/pujas/', admin)
    scratch = [r['id'] for r in body if r['name'].startswith('VerifyDay8')] if body else []
    second = next((i for i in scratch if i != puja_id), None)

    test_cleanup(admin, kit_id, puja_id, second)

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
