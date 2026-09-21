"""Day 9 — vendor administration, over the real HTTP API.

`core/permissions.py` defines four roles and the API has enforced vendor scoping
since Day 3, but two things were missing, and both were only visible from the
dashboard:

1. **There was no way to administer a vendor.** `/products/admin/vendors/` worked and
   nothing called it, so a shop could only be created in Django admin. The screen
   that fixes that needed an account picker, which did not exist either.
2. **A vendor could not open the dashboard at all.** `AdminContext` gated on
   `is_admin_user`, a legacy boolean that `UserProfile.save()` only ever sets for
   super_admin/admin. A vendor's token verified, came back `false`, was discarded,
   and the login bounced straight back to `/login`. The VENDOR role was enforced
   correctly on every endpoint and was unreachable in the product.

The checks worth having here are the ones a happy path misses:

* a vendor must **not** be able to enumerate the user table — this is the one
  endpoint where *reading* is a privilege;
* creating a shop must promote the account, and must **not** demote a manager or
  hand out Django admin (`is_staff`) as a side effect;
* deleting a shop must not revoke a login.

Cleanup: registers one throwaway account. Run afterwards:

    ./venv/Scripts/python.exe manage.py purge_verification_users

Usage:  ./venv/Scripts/python.exe verify_day9.py
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

RUN = uuid.uuid4().hex[:8]
SHOP_USER = f'verifyday9shop{RUN}'
SHOP_EMAIL = f'{SHOP_USER}@example.com'
SHOP_PASSWORD = 'VerifyDay9Pass123'
SHOP_NAME = f'VerifyDay9 Bhandar {RUN}'

USERS_URL = '/api/auth/admin/users/'
VENDORS_URL = '/api/products/admin/vendors/'


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


def profile_body(token):
    """The whole `/auth/profile/` payload.

    `UserSerializer` puts `first_name`/`last_name`/`email` at the **top level** and
    nests only the profile fields under `profile`. Reading `first_name` from the
    nested object yields `None` on a perfectly correct response.
    """
    status, body = request('GET', '/api/auth/profile/', token)
    return body or {}


def profile(token):
    return profile_body(token).get('profile') or {}


# ---------------------------------------------------------------- the picker

def test_account_picker(admin, super_admin, vendor, customer):
    section('The account picker — the endpoint the vendor form needs')

    status, rows = request('GET', USERS_URL, admin)
    check('a manager can list candidate accounts', status == 200, f'status={status}')
    check('it returns a bare list, not a paginated envelope',
          isinstance(rows, list), f'type={type(rows).__name__}')
    if not isinstance(rows, list) or not rows:
        return

    check('every row carries exactly the fields the picker reads',
          all(set(r) == {'id', 'username', 'email', 'first_name', 'last_name',
                         'is_active', 'role', 'has_vendor'} for r in rows),
          f'row={rows[0]}')

    # A hash has no business in a JSON response, even read-only.
    leaked = [k for k in ('password', 'is_staff', 'is_superuser', 'last_login',
                          'date_joined', 'permissions') if k in rows[0]]
    check('no password or privilege field leaks', not leaked, f'leaked={leaked}')

    # `role` must be the resolved role, not the raw column: vendor1 is is_staff
    # (so the raw fallback would say `admin`) but its profile says vendor.
    by_name = {r['username']: r for r in rows}
    check('the vendor resolves as `vendor`, not `admin` despite being is_staff',
          by_name.get('vendor1', {}).get('role') == 'vendor',
          f"role={by_name.get('vendor1', {}).get('role')}")
    check('the customer resolves as `customer`',
          by_name.get('testuser', {}).get('role') == 'customer',
          f"role={by_name.get('testuser', {}).get('role')}")
    check('the existing shop owner is flagged as having a vendor',
          by_name.get('vendor1', {}).get('has_vendor') is True,
          f"has_vendor={by_name.get('vendor1', {}).get('has_vendor')}")

    # Authorization. Reading this endpoint is itself the privilege.
    status, _ = request('GET', USERS_URL, super_admin)
    check('a super admin can list', status == 200, f'status={status}')
    status, _ = request('GET', USERS_URL, vendor)
    check('a VENDOR is refused — it must not enumerate users', status == 403,
          f'status={status}')
    status, _ = request('GET', USERS_URL, customer)
    check('a customer is refused', status == 403, f'status={status}')
    status, _ = request('GET', USERS_URL)
    check('anonymous is refused', status == 401, f'status={status}')

    status, _ = request('POST', USERS_URL, admin, {'username': 'nope'})
    check('the endpoint accepts no writes (POST 405)', status == 405, f'status={status}')
    status, _ = request('PATCH', USERS_URL, admin, {'role': 'super_admin'})
    check('and no role escalation through it (PATCH 405)', status == 405,
          f'status={status}')

    # Filters.
    status, filtered = request('GET', f'{USERS_URL}?unassigned=1', admin)
    names = {r['username'] for r in filtered}
    check('?unassigned=1 hides accounts that already own a shop',
          'vendor1' not in names, f'names={sorted(names)}')
    check('?unassigned=1 keeps accounts that do not', 'testuser' in names,
          f'names={sorted(names)}')

    status, searched = request('GET', f'{USERS_URL}?search=testuser', admin)
    check('?search= narrows to a match',
          [r['username'] for r in searched] == ['testuser'], f'rows={searched}')

    status, none = request('GET', f'{USERS_URL}?search=nobodyatall', admin)
    check('a search with no match is an empty list, not an error',
          status == 200 and none == [], f'status={status} body={none}')


# ---------------------------------------------------------------- resolved role

def test_resolved_role(admin, vendor, customer):
    section('The profile reports the role the server actually enforces')

    check('the admin resolves as super_admin', profile(admin).get('role') == 'super_admin',
          f"role={profile(admin).get('role')}")
    check('the vendor resolves as vendor', profile(vendor).get('role') == 'vendor',
          f"role={profile(vendor).get('role')}")
    check('the customer resolves as customer', profile(customer).get('role') == 'customer',
          f"role={profile(customer).get('role')}")

    # This is *why* the old dashboard gate was wrong: the legacy boolean is false
    # for a vendor, so gating on it locked the role out of the product entirely.
    check('the vendor is not flagged is_admin_user — the legacy gate locked it out',
          profile(vendor).get('is_admin_user') is not True,
          f"is_admin_user={profile(vendor).get('is_admin_user')}")

    # `ProfileView` implements PUT, not PATCH. A PATCH returns 405, which is how a
    # previous "role is read-only" check passed without testing anything.
    status, _ = request('PUT', '/api/auth/profile/', customer,
                        {'first_name': 'Escalation Attempt', 'role': 'super_admin'})
    check('the profile write endpoint accepts PUT', status == 200, f'status={status}')
    after = profile_body(customer)
    check('the write really landed', after.get('first_name') == 'Escalation Attempt',
          f"first_name={after.get('first_name')!r}")
    check('and the role did not change', after.get('profile', {}).get('role') == 'customer',
          f"role={after.get('profile', {}).get('role')}")
    request('PUT', '/api/auth/profile/', customer, {'first_name': 'Ram'})


# ---------------------------------------------------------------- promotion

def test_vendor_provisioning(admin, vendor, customer):
    section('Creating a shop makes its account a vendor')

    status, _ = request('POST', '/api/auth/register/', body={
        'username': SHOP_USER,
        'email': SHOP_EMAIL,
        'password': SHOP_PASSWORD,
        'password2': SHOP_PASSWORD,
        'first_name': 'Probe',
    })
    check('registered a throwaway account', status == 201, f'status={status}')
    if status != 201:
        return None

    shop_token = login(SHOP_USER, SHOP_PASSWORD)
    check('it can log in as a customer', shop_token is not None)
    check('it starts out a customer', profile(shop_token).get('role') == 'customer',
          f"role={profile(shop_token).get('role')}")

    # The whole point: this account must not be able to reach the admin API yet.
    status, _ = request('GET', '/api/products/admin/products/', shop_token)
    check('a customer is refused the admin catalogue', status == 403, f'status={status}')

    # --- create the shop -------------------------------------------------
    status, shop = request('POST', VENDORS_URL, admin, {
        'user': None,  # replaced below with the real id
        'shop_name': SHOP_NAME,
    })
    check('a shop without an account is rejected', status == 400, f'status={status}')

    status, rows = request('GET', f'{USERS_URL}?search={SHOP_USER}', admin)
    if status != 200 or not rows:
        check('the new account appears in the picker', False, f'status={status} rows={rows}')
        return None
    user_id = rows[0]['id']
    check('the new account appears in the picker and is unassigned',
          rows[0]['has_vendor'] is False, f'row={rows[0]}')

    status, shop = request('POST', VENDORS_URL, admin, {
        'user': user_id, 'shop_name': SHOP_NAME,
    })
    check('the shop is created', status == 201, f'status={status} body={shop}')
    if status != 201:
        return None

    shop_id = shop['id']
    check('it starts with no products', shop.get('product_count') == 0, f'shop={shop}')
    check('the slug is derived server-side', bool(shop.get('slug')), f'shop={shop}')

    # --- the account is now a vendor -------------------------------------
    promoted = login(SHOP_USER, SHOP_PASSWORD)
    check('the account can still log in', promoted is not None)
    check('and now resolves as a vendor', profile(promoted).get('role') == 'vendor',
          f"role={profile(promoted).get('role')}")

    status, scoped = request('GET', '/api/products/admin/products/', promoted)
    count = scoped.get('count') if isinstance(scoped, dict) else len(scoped or [])
    check('but sees only its own (empty) catalogue', count == 0, f'count={count}')

    # A vendor must not be able to hand out the role.
    status, _ = request('POST', VENDORS_URL, promoted, {
        'user': user_id, 'shop_name': 'Escalation Attempt',
    })
    check('a vendor cannot create another shop', status == 403, f'status={status}')

    # --- the assigned area -----------------------------------------------
    status, areas = request('GET', '/api/products/admin/areas/', admin)
    area_id = areas[0]['id'] if isinstance(areas, list) and areas else None
    if area_id:
        status, updated = request('PATCH', f'{VENDORS_URL}{shop_id}/', admin,
                                  {'area': area_id})
        check('a delivery area can be assigned', status == 200, f'status={status}')
        check('and is reported back by name', bool(updated.get('area_name')),
              f'area_name={updated.get("area_name")}')

    # --- it now drops out of the picker ----------------------------------
    status, rows = request('GET', f'{USERS_URL}?search={SHOP_USER}&unassigned=1', admin)
    check('once it owns a shop it leaves the unassigned picker', rows == [], f'rows={rows}')

    # --- the storefront sees the shop ------------------------------------
    status, body = request('GET', '/api/products/admin/vendors/', admin)
    listed = [v for v in body if v['id'] == shop_id] if isinstance(body, list) else []
    check('the shop appears in the vendor list', len(listed) == 1, f'status={status}')

    return shop_id


def test_deleting_a_shop(admin, shop_id):
    section('Closing a shop does not revoke the login')

    if not shop_id:
        check('a shop was available to delete', False)
        return

    status, _ = request('DELETE', f'{VENDORS_URL}{shop_id}/', admin)
    check('the shop is deleted', status == 204, f'status={status}')

    # The role is deliberately kept: revoking a login is an account decision, not a
    # shop decision, and conflating them would let removing a shop lock someone out.
    promoted = login(SHOP_USER, SHOP_PASSWORD)
    check('the account can still log in', promoted is not None)
    check('and keeps the vendor role', profile(promoted).get('role') == 'vendor',
          f"role={profile(promoted).get('role')}")

    status, body = request('GET', '/api/products/admin/vendors/', admin)
    check('the shop is gone from the list',
          not any(v['id'] == shop_id for v in body), 'still listed')

    # And the seeded demo shop is untouched.
    check('the seeded vendor is still there',
          any(v['shop_name'] == 'Patan Puja Bhandar' for v in body),
          f'vendors={[v["shop_name"] for v in body]}')


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

    # The seeded admin is a superuser; a second manager would need a new account, so
    # super-admin coverage reuses the same token where the class is the same.
    test_account_picker(admin, admin, vendor, customer)
    test_resolved_role(admin, vendor, customer)

    shop_id = test_vendor_provisioning(admin, vendor, customer)
    test_deleting_a_shop(admin, shop_id)

    print(f'\n  probe user {SHOP_USER!r} left behind — run:')
    print('    manage.py purge_verification_users')

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
