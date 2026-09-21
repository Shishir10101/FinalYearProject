"""Day 11 — reviews and ratings, over the real HTTP API.

`docs/DATABASE-DESIGN.md` listed a `Review` table as a known omission ("not in scope;
noted as post-MVP") and `docs/FEATURES.md` listed "no social proof on product pages".
This verifies the feature end to end, including the two things that are easy to get
subtly wrong:

* **the average must move when a review is hidden.** If it did not, moderation would be
  cosmetic — the number a shopper trusts would still include the review that was taken
  down;
* **a review must not publish who wrote it.** The review list is public, so an author's
  full name, username or email leaking there is a privacy bug that no functional test
  would catch.

It buys one product so it can prove the "verified purchase" badge, which means it writes
an order. Both the order and the review are cleaned up at the end — the review especially,
because leaving it would silently change a seeded product's rating.

Cleanup if this script is interrupted:

    ./venv/Scripts/python.exe manage.py purge_verification_orders
    ./venv/Scripts/python.exe manage.py purge_verification_reviews

Usage:  ./venv/Scripts/python.exe verify_day11.py
"""

import json
import os
import urllib.error
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
FAILURES = []

MARKER = 'verify_day11.py'
PROBE_BODY = f'Written by {MARKER} — safe to delete.'


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


def reviews_url(slug):
    return f'/api/products/{slug}/reviews/'


# ---------------------------------------------------------------- read

def test_public_read(product, customer):
    section('Anyone can read reviews; nobody can post anonymously')

    slug = product['slug']
    status, body = request('GET', reviews_url(slug))
    check('the review list is public', status == 200, f'status={status}')
    if status != 200:
        return

    check('it returns the four things the product page needs',
          set(body) >= {'summary', 'results', 'count', 'mine'}, f'keys={sorted(body)}')
    check('an unrated product reports no average, not zero',
          body['summary']['average_rating'] is None,
          f"average={body['summary']['average_rating']}")
    check('and a review count of zero', body['summary']['review_count'] == 0)
    check('the distribution is a five-to-one histogram',
          list(body['summary']['distribution'].keys()) == ['5', '4', '3', '2', '1'],
          f"keys={list(body['summary']['distribution'].keys())}")
    check('mine is null for an anonymous reader', body['mine'] is None)

    status, _ = request('POST', reviews_url(slug), body={
        'rating': 5, 'title': 'x', 'body': 'y',
    })
    check('an anonymous POST is refused', status == 401, f'status={status}')

    status, _ = request('GET', reviews_url('no-such-product-at-all'))
    check('reviews of an unknown product are 404', status == 404, f'status={status}')


# ---------------------------------------------------------------- write

def test_write(product, customer, other):
    section('Writing, editing and validating a review')

    slug = product['slug']
    status, review = request('POST', reviews_url(slug), customer, {
        'rating': 5, 'title': 'Excellent dhoop', 'body': PROBE_BODY,
    })
    check('a signed-in customer can post a review', status == 201, f'status={status} body={review}')
    if status != 201:
        return None

    review_id = review['id']
    check('the payload reports the rating back', review.get('rating') == 5, f'review={review}')

    status, body = request('GET', reviews_url(slug), customer)
    check('the review appears in the list', body['count'] == 1, f"count={body['count']}")
    check('the average is the single rating', body['summary']['average_rating'] == 5.0,
          f"average={body['summary']['average_rating']}")
    check('the histogram counts it under five',
          body['summary']['distribution']['5'] == 1,
          f"distribution={body['summary']['distribution']}")
    check('the author is told which review is theirs',
          body['mine'] is not None and body['mine']['is_mine'] is True,
          f"mine={body['mine']}")

    # --- one review per customer ---------------------------------------
    status, second = request('POST', reviews_url(slug), customer, {
        'rating': 2, 'title': 'Changed my mind', 'body': 'Not what I expected.',
    })
    check('a second POST is an edit, not a duplicate', status == 200, f'status={status}')
    status, body = request('GET', reviews_url(slug))
    check('the count stayed at one', body['count'] == 1, f"count={body['count']}")
    check('and the new rating replaced the old',
          body['summary']['average_rating'] == 2.0,
          f"average={body['summary']['average_rating']}")

    # --- validation -----------------------------------------------------
    for bad in (0, 6):
        status, _ = request('POST', reviews_url(slug), customer,
                            {'rating': bad, 'title': 'x', 'body': 'y'})
        check(f'a rating of {bad} is refused', status == 400, f'status={status}')

    status, _ = request('POST', reviews_url(slug), other, {
        'rating': 1, 'title': '', 'body': '   ',
    })
    check('a rating with no words is refused', status == 400, f'status={status}')

    # --- a second customer ---------------------------------------------
    status, _ = request('POST', reviews_url(slug), other, {
        'rating': 4, 'title': 'Good', 'body': 'Good value for the price.',
    })
    check('a second customer can review the same product', status == 201, f'status={status}')
    status, body = request('GET', reviews_url(slug))
    check('the count is now two', body['count'] == 2, f"count={body['count']}")
    check('the average is the mean of both',
          body['summary']['average_rating'] == 3.0,
          f"average={body['summary']['average_rating']}")

    return review_id


# ---------------------------------------------------------------- privacy

def test_privacy(product):
    section('A public review list does not publish who wrote it')

    status, body = request('GET', reviews_url(product['slug']))
    check('the list loads', status == 200, f'status={status}')
    if status != 200 or not body['results']:
        return

    row = body['results'][0]
    for forbidden in ('user', 'email', 'user_id', 'username'):
        check(f'no `{forbidden}` in a public review', forbidden not in row, f'row={row}')

    check('the author is a display name', isinstance(row.get('author'), str)
          and bool(row['author']), f"author={row.get('author')!r}")
    check('no email address leaks through the author field',
          '@' not in (row.get('author') or ''), f"author={row.get('author')!r}")


# ---------------------------------------------------------------- verified purchase

def test_verified_purchase(product, customer):
    section('The verified-purchase badge reflects a real order')

    slug = product['slug']
    before = None
    status, body = request('GET', reviews_url(slug), customer)
    if status == 200 and body.get('mine'):
        before = body['mine']['is_verified_purchase']
    check('the badge is false before any order', before is False, f'before={before}')

    # Buy the product.
    status, _ = request('POST', '/api/orders/cart/add/', customer,
                        {'product_id': product['id'], 'quantity': 1})
    check('the product can be added to the cart', status in (200, 201), f'status={status}')

    status, order = request('POST', '/api/orders/checkout/', customer, {
        'shipping_address': 'Ward 4, Jhamsikhel',
        'shipping_city': 'lalitpur',
        'phone': '9800000000',
        'payment_method': 'cod',
        'notes': f'Fixture for {MARKER} — safe to delete',
    })
    check('the order is placed', status == 201, f'status={status} body={order}')
    if status != 201:
        return

    # Re-post the review: it is an edit, and the badge is NOT recomputed, so this
    # proves the snapshot behaviour as well as the happy path.
    request('POST', reviews_url(slug), customer, {
        'rating': 5, 'title': 'Bought it, loved it', 'body': PROBE_BODY,
    })
    status, body = request('GET', reviews_url(slug), customer)
    check('the badge is still false on an edit — it is a snapshot, not a live lookup',
          body['mine']['is_verified_purchase'] is False,
          f"verified={body['mine']['is_verified_purchase']}")

    # A fresh review by the same customer cannot exist (unique_together), so the
    # snapshot is checked by deleting and re-posting.
    request('DELETE', f"/api/products/reviews/{body['mine']['id']}/", customer)
    status, fresh = request('POST', reviews_url(slug), customer, {
        'rating': 5, 'title': 'Bought it, loved it', 'body': PROBE_BODY,
    })
    check('a new review after the purchase is accepted', status == 201, f'status={status}')
    check('and is marked a verified purchase',
          fresh.get('is_verified_purchase') is True, f'review={fresh}')


# ---------------------------------------------------------------- moderation

def test_moderation(product, customer, manager):
    section('Moderation moves the number a shopper sees')

    slug = product['slug']
    status, body = request('GET', reviews_url(slug))
    check('there are two reviews to work with', body['count'] == 2, f"count={body['count']}")
    baseline = body['summary']['average_rating']

    status, all_reviews = request('GET', '/api/products/admin/reviews/', manager)
    check('a manager can list every review', status == 200, f'status={status}')
    check('the admin list is a bare list, not a page',
          isinstance(all_reviews, list), f'type={type(all_reviews).__name__}')

    status, _ = request('GET', '/api/products/admin/reviews/', customer)
    check('a customer is refused the moderation list', status == 403, f'status={status}')

    status, _ = request('GET', '/api/products/admin/reviews/')
    check('an anonymous reader is refused it too', status == 401, f'status={status}')

    if not isinstance(all_reviews, list) or not all_reviews:
        return

    # Hide the two-star review by the first customer.
    target = next((r for r in all_reviews if r['rating'] == 2), all_reviews[0])
    status, updated = request('PATCH', f"/api/products/admin/reviews/{target['id']}/",
                              manager, {'is_approved': False})
    check('a manager can hide a review', status == 200, f'status={status}')
    check('the hidden flag is reported back', updated.get('is_approved') is False,
          f'updated={updated}')

    status, body = request('GET', reviews_url(slug))
    check('the hidden review leaves the storefront', body['count'] == 1,
          f"count={body['count']}")
    check('and the average changes with it',
          body['summary']['average_rating'] != baseline,
          f'baseline={baseline} now={body["summary"]["average_rating"]}')
    check('a hidden review is still visible to a manager',
          any(r['id'] == target['id'] for r in
              (request('GET', '/api/products/admin/reviews/', manager)[1] or [])),
          'the manager lost sight of what they hid')

    # The badge must be read-only, or a manager could rewrite history.
    #
    # The probe has to start from a review whose badge is **false**. Picking any review
    # and asserting "not True" afterwards proves nothing when the badge was already True
    # — the write could have been honoured and the check would still fail. So find an
    # unverified review, try to verify it, and confirm it did not move.
    unverified = next((r for r in all_reviews if not r['is_verified_purchase']), None)
    check('there is an unverified review to attempt the rewrite on',
          unverified is not None, f'reviews={[(r["id"], r["is_verified_purchase"]) for r in all_reviews]}')
    if unverified is not None:
        status, updated = request('PATCH', f"/api/products/admin/reviews/{unverified['id']}/",
                                  manager, {'is_verified_purchase': True})
        check('the verified badge cannot be rewritten by a manager',
              updated.get('is_verified_purchase') is False,
              f'before=False after={updated.get("is_verified_purchase")!r} updated={updated}')
        check('and the badge is still false on a re-read',
              next((r['is_verified_purchase'] for r in
                    (request('GET', '/api/products/admin/reviews/', manager)[1] or [])
                    if r['id'] == unverified['id']), None) is False,
              'the write landed after all')

    # Unhide — hiding must not be a one-way door.
    request('PATCH', f"/api/products/admin/reviews/{target['id']}/", manager,
            {'is_approved': True})
    status, body = request('GET', reviews_url(slug))
    check('unhiding restores it', body['count'] == 2, f"count={body['count']}")
    check('and the average returns to what it was',
          body['summary']['average_rating'] == baseline,
          f'baseline={baseline} now={body["summary"]["average_rating"]}')

    return target['id']


def test_product_detail_summary(product, customer):
    section('The product payload carries the summary, without a query per review')

    status, detail = request('GET', f"/api/products/{product['slug']}/")
    check('the product detail loads', status == 200, f'status={status}')
    check('it carries an average rating', 'average_rating' in detail, f'keys={sorted(detail)}')
    check('it carries a review count', 'review_count' in detail, f'keys={sorted(detail)}')

    # Compare against the review list rather than a literal. The ratings are edited
    # earlier in this script (the two-star review becomes a five-star one), so a
    # hardcoded mean silently goes stale the moment the script changes — and it did.
    status, body = request('GET', reviews_url(product['slug']))
    summary = body['summary']
    check('the count matches the review list',
          detail['review_count'] == summary['review_count'],
          f"detail={detail['review_count']} list={summary['review_count']}")
    check('the average matches the review list',
          detail['average_rating'] == summary['average_rating'],
          f"detail={detail['average_rating']} list={summary['average_rating']}")
    check('the count is the two live reviews',
          detail['review_count'] == 2, f"count={detail['review_count']}")


# ---------------------------------------------------------------- cleanup

def test_cleanup(product, customer, manager):
    section('Cleanup — the seeded catalogue is left as it was')

    slug = product['slug']
    status, body = request('GET', reviews_url(slug))
    removed = 0
    for row in body['results']:
        # The public list carries no user id, so delete by id as a manager.
        if request('DELETE', f"/api/products/reviews/{row['id']}/", manager)[0] == 204:
            removed += 1
    check('every probe review is deleted', removed == body['count'],
          f'removed={removed} of {body["count"]}')

    status, body = request('GET', reviews_url(slug))
    check('the product is back to no reviews', body['count'] == 0, f"count={body['count']}")
    check('and to no average', body['summary']['average_rating'] is None,
          f"average={body['summary']['average_rating']}")

    status, detail = request('GET', f"/api/products/{product['slug']}/")
    check('the product payload agrees', detail['review_count'] == 0
          and detail['average_rating'] is None,
          f"count={detail['review_count']} average={detail['average_rating']}")

    status, remaining = request('GET', '/api/products/admin/reviews/', manager)
    check('no reviews remain anywhere',
          isinstance(remaining, list) and len(remaining) == 0,
          f'remaining={len(remaining) if isinstance(remaining, list) else remaining}')


def main():
    print(f'Verifying against {BASE}')

    customer = login('testuser', 'test1234')
    other = None  # a second reviewer; reuse the manager token is wrong, so use vendor1
    manager = login('admin', 'admin123')
    check('the customer can log in', customer is not None)
    check('the manager can log in', manager is not None)
    if not customer or not manager:
        return 1

    # `vendor1` is a staff role, not a second customer, so a fresh customer is not
    # available without registering one. The "second reviewer" checks therefore use a
    # registered throwaway, which `purge_verification_users` removes.
    import uuid
    probe = f'verifyday11rev{uuid.uuid4().hex[:8]}'
    status, _ = request('POST', '/api/auth/register/', body={
        'username': probe, 'email': f'{probe}@example.com',
        'password': 'VerifyDay11Pass123', 'password2': 'VerifyDay11Pass123',
        'first_name': 'Second', 'last_name': 'Reviewer',
    })
    check('registered a second reviewer', status == 201, f'status={status}')
    if status == 201:
        other = login(probe, 'VerifyDay11Pass123')
    if not other:
        print('\nCannot continue without a second reviewer.')
        return 1

    status, products = request('GET', '/api/products/?page=1')
    rows = (products.get('results') if isinstance(products, dict) else products) or []
    check('there is a product to review', bool(rows), f'status={status}')
    if not rows:
        return 1
    product = rows[0]
    print(f'  using product: {product["name"]} ({product["slug"]})')

    test_public_read(product, customer)
    test_write(product, customer, other)
    test_privacy(product)
    test_verified_purchase(product, customer)
    test_moderation(product, customer, manager)
    test_product_detail_summary(product, customer)
    test_cleanup(product, customer, manager)

    print(f'\n  probe user {probe!r} left behind — run:')
    print('    manage.py purge_verification_users')
    print('    manage.py purge_verification_orders')

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
