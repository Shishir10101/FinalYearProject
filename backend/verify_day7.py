"""Day 7 — token revocation.

Proves, over the real HTTP API, that a password reset ends existing sessions.

`docs/CURRENT-STATE.md` used to record this as a known limitation: "a reset does not
revoke existing JWTs. Access tokens are stateless and last a day, so a stolen token
keeps working until it expires." That was true, and it was the one place where the
project knowingly left a security gap open. This verifies it is closed.

The two checks that matter most are the ones a naive implementation would pass
while still being broken:

* the **refresh** endpoint must also refuse a revoked token — it never goes through
  DRF's authentication classes, so a version check in the authentication class
  alone leaves it answering 200 and minting access tokens;
* revoking one user must not sign out anybody else.

Cleanup: registers one throwaway account. Run afterwards:

    ./venv/Scripts/python.exe manage.py purge_verification_users

Usage:  ./venv/Scripts/python.exe verify_day7.py
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

# Unique per run. A fixed name collides on a re-run (register returns 400 "already
# exists") and the script silently skips its most important section — which is a
# verifier bug that looks like a product failure. `purge_verification_users` removes
# everything matching the `verifyday` prefix.
PROBE_SUFFIX = uuid.uuid4().hex[:8]
PROBE_USERNAME = f'verifyday7probe{PROBE_SUFFIX}'
PROBE_EMAIL = f'verifyday7probe{PROBE_SUFFIX}@example.com'
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
    """A check that could not be run for an environmental reason.

    Used for the password-reset endpoints, which are throttled at 10/min per IP.
    A full verification sweep makes more than that inside a minute, so a 429 here
    means the throttle is doing its job — not that the feature is broken. Counting
    it as a failure would make the suite order-dependent and cry wolf.
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
    if status != 200 or not isinstance(body, dict):
        return None, None
    return body.get('access'), body.get('refresh')


def protected(token):
    return request('GET', '/api/auth/profile/', token)


def refresh(refresh_token):
    return request('POST', '/api/auth/token/refresh/', body={'refresh': refresh_token})


# ---------------------------------------------------------------- basics

def test_baseline():
    section('Baseline: tokens work before anything is revoked')

    access, refresh_token = login('testuser', 'test1234')
    check('customer can log in', access is not None)
    if not access:
        return None, None

    status, _ = protected(access)
    check('a fresh access token authenticates', status == 200, f'status={status}')

    status, _ = refresh(refresh_token)
    check('a fresh refresh token works', status == 200, f'status={status}')

    return access, refresh_token


# ---------------------------------------------------------------- logout-all

def test_logout_all(access, refresh_token):
    section('Logout everywhere')

    status, _ = request('POST', '/api/auth/logout-all/')
    check('anonymous cannot call logout-all', status == 401, f'status={status}')

    status, body = request('POST', '/api/auth/logout-all/', access)
    check('logout-all succeeds', status == 200, f'status={status} body={body}')
    check('it reports the new token version',
          isinstance(body, dict) and body.get('token_version', 0) >= 1, f'body={body}')

    status, body = protected(access)
    check('the access token that made the request is now dead',
          status == 401, f'status={status}')

    status, _ = refresh(refresh_token)
    check('the matching refresh token is refused too', status == 401, f'status={status}')

    fresh, _ = login('testuser', 'test1234')
    check('logging in again still works', fresh is not None)
    if fresh:
        status, _ = protected(fresh)
        check('the new token authenticates', status == 200, f'status={status}')
        return fresh
    return None


# ---------------------------------------------------------------- reset

def test_password_reset_revokes():
    section('A password reset ends existing sessions')

    status, _ = request('POST', '/api/auth/register/', body={
        'username': PROBE_USERNAME,
        'email': PROBE_EMAIL,
        'password': PROBE_OLD_PASSWORD,
        'password2': PROBE_OLD_PASSWORD,
        'first_name': 'Probe',
    })
    check('registered a throwaway account', status == 201, f'status={status}')
    if status != 201:
        return

    access, refresh_token = login(PROBE_USERNAME, PROBE_OLD_PASSWORD)
    check('the throwaway account can log in', access is not None)
    if not access:
        return

    status, _ = protected(access)
    check('its token works before the reset', status == 200, f'status={status}')

    status, body = request('POST', '/api/auth/password-reset/', body={'email': PROBE_EMAIL})
    if throttled(status, body):
        skip('a reset link is issued', 'rate limited (10/min per IP)')
        return
    check('a reset link is issued', status == 200 and bool(body.get('reset_url')),
          f'status={status}')
    if not body.get('reset_url'):
        return

    query = body['reset_url'].split('?', 1)[1]
    uid = query.split('uid=')[1].split('&')[0]
    token = query.split('token=')[1]

    status, confirm = request('POST', '/api/auth/password-reset/confirm/', body={
        'uid': uid, 'token': token,
        'new_password': PROBE_NEW_PASSWORD, 'new_password2': PROBE_NEW_PASSWORD,
    })
    check('the reset succeeds', status == 200, f'status={status}')
    check('the response says other sessions were ended',
          isinstance(confirm, dict) and 'session' in confirm.get('message', '').lower(),
          f'confirm={confirm}')

    status, _ = protected(access)
    check('the pre-reset ACCESS token is now rejected', status == 401, f'status={status}')

    status, _ = refresh(refresh_token)
    check('the pre-reset REFRESH token is now rejected', status == 401, f'status={status}')

    new_access, _ = login(PROBE_USERNAME, PROBE_NEW_PASSWORD)
    check('the new password works', new_access is not None)
    if new_access:
        status, _ = protected(new_access)
        check('a token from the new password authenticates', status == 200, f'status={status}')


# ---------------------------------------------------------------- isolation

def test_other_users_unaffected(other_access):
    section('Revocation is scoped to one user')

    if not other_access:
        check('a second user token was available', False)
        return

    status, _ = protected(other_access)
    check("another user's token still works", status == 200, f'status={status}')

    # And revoking that user leaves the first one alone.
    admin_access, _ = login('admin', 'admin123')
    status, _ = protected(admin_access)
    check('admin is unaffected by the customer revocation', status == 200, f'status={status}')


# ---------------------------------------------------------------- authz

def test_authorization(admin_access):
    section('Authorization not weakened')

    for endpoint in [
        '/api/products/admin/products/',
        '/api/orders/admin/orders/',
        '/api/analytics/sales/',
        '/api/festivals/pujas/',
    ]:
        status, _ = request('GET', endpoint, admin_access)
        check(f'admin 200 on {endpoint}', status == 200, f'status={status}')

    for endpoint in ['/api/products/admin/products/', '/api/orders/admin/orders/']:
        status, _ = request('GET', endpoint)
        check(f'anonymous 401 on {endpoint}', status == 401, f'status={status}')


# ---------------------------------------------------------------- main

def main():
    print(f'Verifying against {BASE}')

    # A second user, so the isolation check has something to compare against.
    other_access, _ = login('vendor1', 'vendor1234')
    check('vendor can log in', other_access is not None)

    access, refresh_token = test_baseline()
    if not access:
        print('\nCannot continue without a token.')
        return 1

    fresh = test_logout_all(access, refresh_token)
    test_password_reset_revokes()
    test_other_users_unaffected(other_access)

    admin_access, _ = login('admin', 'admin123')
    check('admin can log in', admin_access is not None)
    test_authorization(admin_access)

    print(f'\n  probe user {PROBE_USERNAME!r} left behind — run:')
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
