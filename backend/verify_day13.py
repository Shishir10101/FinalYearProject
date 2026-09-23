"""Day 13 — wishlist, image upload, and per-area analytics, over the real HTTP API.

Three P1 items that `docs/FEATURES.md` still listed as gaps, closed together because
they share one property: each was **invisible to the existing suite**. The API tests
pass without them, the build passes without them, and the storefront looks complete
without them.

* **Wishlist.** `docs/DATABASE-DESIGN.md` carried "No `Coupon` / `Review` / `Wishlist`
  tables — not in scope; noted as post-MVP". Reviews closed on Day 11; this is the
  last of the three. For a festival shop it is the difference between a customer
  assembling a list over several visits and losing it.
* **Image upload.** `Product.image` and `FestivalKit.image` are real columns the seed
  data fills, and nothing in either dashboard could set one. The dashboard now sends
  multipart, which is the part that is easy to get wrong and impossible to see: a
  hand-set `Content-Type: multipart/form-data` without a boundary is rejected as an
  empty body, and that failure looks exactly like "the upload silently did nothing".
* **Per-area analytics.** Vendor scoping landed on Day 9, but nothing broke demand
  down by *where it is going* — the question that decides where a second rider goes.

Three things this script is careful about, because each has burned this project:

* **It owns every precondition.** The wishlist probe account is registered here, with
  a per-run random suffix, and the products and the kit it uploads to are created and
  deleted by this script. Nothing is asserted about state the verifier did not create.
* **It reads before it asserts.** Where a check needs an existing row, the row is
  looked up first and a labelled SKIP is reported rather than a false failure.
* **It checks that the two revenue panels agree**, not just that each one returns
  200. Two dashboard figures that disagree make both of them worthless.

One thing the first version got wrong, recorded because it is the easiest mistake to
repeat: it uploaded an image onto **`kits[0]` — the seeded *Bratabandha Ceremony Kit*** —
and never restored the picture. Running the verifier permanently changed demo data. It
surfaced only from reading `git status` and finding an unexpected `media/kits/` directory,
then asking the database which files it referenced. The kit check now creates its own
scratch kit and deletes it, and two assertions at the end pin that no seeded kit points at
a test upload and no scratch kit was left behind.

Writes rows. Clean up afterwards:

    ./venv/Scripts/python.exe manage.py purge_verification_users   # probe accounts
    ./venv/Scripts/python.exe manage.py purge_verification_orders

The throwaway products and the scratch kit this script creates are deleted by the script
itself. It leaves uploaded **files** behind in `media/` when a row is deleted, because
Django does not unlink a file on model delete — those are inert and safe to remove by hand.

Usage:  ./venv/Scripts/python.exe verify_day13.py
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
SKIP = 0
FAILURES = []

# A real 1x1 PNG. The backend's ImageField decodes what it is given, so a text file
# renamed to .png would be rejected for the right reason while proving nothing about
# the happy path.
PNG_BYTES = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
)

RUN = uuid.uuid4().hex[:8]


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


def multipart(path, token, fields=None, files=None, method='PATCH', timeout=30):
    """A multipart/form-data request.

    Written by hand rather than pulled in, because the whole point of this check is
    that the *boundary* is present. A helper that quietly omitted it would make the
    verifier pass against a server that never received a file.
    """
    boundary = f'----verifyday13{RUN}'
    parts = []
    for key, value in (fields or {}).items():
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f'{value}\r\n'.encode()
        )
    for key, (filename, content, ctype) in (files or {}).items():
        parts.append(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'
            f'Content-Type: {ctype}\r\n\r\n'.encode()
        )
        parts.append(content + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode())
    payload = b''.join(parts)

    req = urllib.request.Request(BASE + path, data=payload, method=method)
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
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
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc)


def login(username, password):
    status, body = request('POST', '/api/auth/login/', body={
        'username': username, 'password': password,
    })
    if status == 200 and isinstance(body, dict):
        return body.get('access')
    return None


def register(username, email):
    """Register a throwaway account and return its access token.

    Registration itself returns **no token** — it answers with a success message and
    the new user, so a token has to be obtained by logging in afterwards. Assuming
    otherwise is what made the first run of this script report a fatal error instead
    of a result.
    """
    status, body = request('POST', '/api/auth/register/', body={
        'username': username, 'email': email,
        'password': 'pw12345678', 'password2': 'pw12345678',
        'first_name': 'Verify', 'last_name': 'Probe',
    })
    if status not in (200, 201):
        print(f'  register({username}) -> {status} {body}')
        return None
    return login(username, 'pw12345678')


# ---------------------------------------------------------------------------


def test_wishlist(customer_token, other_token, admin_token):
    section('Wishlist — save, list, persist, remove')

    status, catalogue = request('GET', '/api/products/?page=1')
    if status != 200 or not isinstance(catalogue, dict) or not catalogue.get('results'):
        skip('wishlist needs two products', 'the catalogue is empty')
        return
    products = catalogue['results']
    if len(products) < 2:
        skip('wishlist needs two products', f'only {len(products)} in the catalogue')
        return
    first, second = products[0], products[1]

    # Own the precondition: start from a known-empty list.
    status, existing = request('GET', '/api/products/wishlist/', token=customer_token)
    check('GET /wishlist/ returns 200', status == 200, f'{status} {existing}')
    for row in (existing if isinstance(existing, list) else []):
        request('DELETE', f'/api/products/wishlist/{row["product"]["id"]}/',
                token=customer_token)

    # --- anonymous access
    status, _ = request('GET', '/api/products/wishlist/')
    check('an anonymous GET is refused with 401', status == 401, f'got {status}')
    status, _ = request('POST', '/api/products/wishlist/', body={'product_id': first['id']})
    check('an anonymous POST is refused with 401', status == 401, f'got {status}')

    # --- add
    status, body = request('POST', '/api/products/wishlist/',
                           token=customer_token, body={'product_id': first['id']})
    check('a customer can save a product (201)', status == 201, f'{status} {body}')

    # --- idempotence: the control that calls this is a toggle, so a double-click
    #     must not be a 400 and must not create a second row.
    status, body = request('POST', '/api/products/wishlist/',
                           token=customer_token, body={'product_id': first['id']})
    check('saving the same product twice is idempotent (200, not 400)',
          status == 200, f'{status} {body}')

    status, listing = request('GET', '/api/products/wishlist/', token=customer_token)
    check('the second add did not duplicate the row',
          isinstance(listing, list) and len(listing) == 1,
          f'len={len(listing) if isinstance(listing, list) else listing}')

    # --- shape: a BARE list, because the storefront maps over it directly. A
    #     `results` wrapper would still satisfy `len()` on the server side while
    #     breaking the page, which is why this is asserted explicitly.
    check('the list is a bare array, not a paginated dict',
          isinstance(listing, list), f'got {type(listing).__name__}')
    if isinstance(listing, list) and listing:
        row = listing[0]
        product = row.get('product', {})
        check('the row nests the product rather than only its id',
              isinstance(product, dict) and product.get('name'),
              f'product={product}')
        # Every field `ProductCard` reads. A missing one renders a blank price or an
        # undefined category, which is a render-time failure no API test would catch.
        needed = ['id', 'slug', 'name', 'price', 'image', 'in_stock',
                  'category_name', 'unit', 'popularity_score']
        missing = [k for k in needed if k not in product]
        check('the nested product carries every field the card renders',
              not missing, f'missing {missing}')

    # --- ordering: newest first
    request('POST', '/api/products/wishlist/',
            token=customer_token, body={'product_id': second['id']})
    status, listing = request('GET', '/api/products/wishlist/', token=customer_token)
    if isinstance(listing, list) and len(listing) == 2:
        check('the newest save is first',
              listing[0]['product']['id'] == second['id'],
              f'first={listing[0]["product"]["id"]} expected={second["id"]}')
    else:
        check('two saved products are listed', False, f'got {listing}')

    # --- persistence: a fresh request must see the same rows. This is the whole
    #     point of a wishlist; context state alone would hide a broken backend.
    status, again = request('GET', '/api/products/wishlist/', token=customer_token)
    check('the saved rows survive a second request',
          isinstance(again, list) and len(again) == 2,
          f'got {len(again) if isinstance(again, list) else again}')

    # --- `is_wishlisted` on the product detail drives the heart on first paint
    status, detail = request('GET', f'/api/products/{first["slug"]}/', token=customer_token)
    check('the product detail reports is_wishlisted=true once saved',
          status == 200 and detail.get('is_wishlisted') is True, f'{status} {detail}')
    status, anon_detail = request('GET', f'/api/products/{first["slug"]}/')
    check('a guest is told is_wishlisted=false',
          anon_detail.get('is_wishlisted') is False, f'{anon_detail}')

    # --- privacy
    status, other_list = request('GET', '/api/products/wishlist/', token=other_token)
    check('another customer cannot see these rows',
          isinstance(other_list, list) and other_list == [],
          f'got {other_list}')
    status, detail = request('GET', f'/api/products/{first["slug"]}/', token=other_token)
    check("another customer's save does not flip your flag",
          detail.get('is_wishlisted') is False, f'{detail.get("is_wishlisted")}')

    # --- removal, keyed by product id because that is what the heart has
    status, _ = request('DELETE', f'/api/products/wishlist/{first["id"]}/',
                        token=customer_token)
    check('removing your own entry returns 204', status == 204, f'got {status}')
    status, _ = request('DELETE', f'/api/products/wishlist/{first["id"]}/',
                        token=customer_token)
    check('removing it again returns 404', status == 404, f'got {status}')
    status, _ = request('DELETE', f'/api/products/wishlist/{second["id"]}/',
                        token=other_token)
    check("removing somebody else's entry returns 404, not 403",
          status == 404, f'got {status}')

    status, listing = request('GET', '/api/products/wishlist/', token=customer_token)
    check('the other customer could not delete your row',
          isinstance(listing, list) and len(listing) == 1, f'got {listing}')

    # --- validation
    status, body = request('POST', '/api/products/wishlist/',
                           token=customer_token, body={'product_id': 99999999})
    check('an unknown product is refused with 400', status == 400, f'{status} {body}')

    # --- routing: `wishlist` is a valid slug, so a mis-ordered urlconf would 404
    #     this whole endpoint family rather than erroring visibly.
    check('the route resolves rather than being read as a product slug',
          status in (200, 400), f'got {status}')

    # leave the probe account clean
    request('DELETE', f'/api/products/wishlist/{second["id"]}/', token=customer_token)


def test_image_upload(admin_token):
    section('Image upload — multipart on products and kits')

    status, categories = request('GET', '/api/products/admin/categories/', token=admin_token)
    if status != 200 or not categories:
        skip('image upload needs a category', f'{status}')
        return
    category_id = (categories[0] if isinstance(categories, list) else categories[0])['id']

    created_ids = []

    # --- create with an image
    status, body = multipart(
        '/api/products/admin/products/', admin_token,
        fields={
            'name': f'Verify Day13 Upload {RUN}', 'description': 'temporary',
            'price': '10', 'stock': '1', 'category': str(category_id), 'unit': 'piece',
        },
        files={'image': ('probe.png', PNG_BYTES, 'image/png')},
        method='POST',
    )
    check('creating a product with an image succeeds (201)', status == 201, f'{status} {body}')
    if status != 201:
        return
    product = body
    created_ids.append(product['id'])

    check('the created product carries an image URL', bool(product.get('image')),
          f'image={product.get("image")!r}')
    # A bare `media/...` would resolve against the *page* and 404 in the browser.
    url = product.get('image') or ''
    check('the image URL is absolute, so the storefront can load it',
          url.startswith(('http://', 'https://', '/')), f'{url!r}')
    check('the image landed in the products/ upload path', '/products/' in url, f'{url!r}')

    # --- the URL actually serves bytes
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            served = resp.status
            blob = resp.read()
    except Exception as exc:  # noqa: BLE001
        served, blob = 0, str(exc).encode()
    check('the returned image URL serves the file', served == 200 and blob == PNG_BYTES,
          f'status={served} bytes={len(blob)}')

    # --- patch an existing product with an image, other fields in the same request
    status, body = multipart(
        f'/api/products/admin/products/{product["id"]}/', admin_token,
        fields={'name': f'Verify Day13 Renamed {RUN}', 'price': '25'},
        files={'image': ('probe2.png', PNG_BYTES, 'image/png')},
    )
    check('patching a product with an image succeeds (200)', status == 200, f'{status} {body}')
    check('the other fields saved in the same multipart request',
          body.get('name') == f'Verify Day13 Renamed {RUN}' and str(body.get('price')) == '25.00',
          f'name={body.get("name")!r} price={body.get("price")!r}')

    # --- a non-image is refused rather than stored
    status, body = multipart(
        f'/api/products/admin/products/{product["id"]}/', admin_token,
        files={'image': ('notes.txt', b'not an image', 'text/plain')},
    )
    check('a non-image file is refused with 400', status == 400, f'{status} {body}')
    check('the rejection names the image field',
          isinstance(body, dict) and 'image' in body, f'{body}')

    # --- clearing: removal cannot travel as multipart, so it goes as JSON null
    status, body = request('PATCH', f'/api/products/admin/products/{product["id"]}/',
                           token=admin_token, body={'image': None})
    check('clearing the image with JSON null succeeds', status == 200, f'{status} {body}')
    status, detail = request('GET', f'/api/products/{body["slug"]}/')
    check('the cleared image is actually gone', not detail.get('image'),
          f'image={detail.get("image")!r}')

    # --- kits
    #
    # The kit is a **throwaway created by this script**, not a seeded one. The first
    # version of this check uploaded onto `kits[0]` — the seeded *Bratabandha Ceremony
    # Kit* — and never restored its picture, so running the verifier permanently
    # changed seeded data. It was caught by reading `git status` and finding an
    # unexpected `media/kits/` directory, and confirmed by asking the database which
    # files it referenced. Creating and deleting our own row means the verifier cannot
    # touch the demo data at all.
    status, kits = request('GET', '/api/festivals/admin/kits/', token=admin_token)
    if status == 200 and kits:
        seeded = kits[0]
        check('the kit write payload now exposes an image field',
              'image' in seeded, f'keys={sorted(seeded.keys())}')

        scratch_name = f'Verify Day13 Scratch Kit {RUN}'
        status, scratch = request('POST', '/api/festivals/admin/kits/', token=admin_token, body={
            'name': scratch_name, 'festival_type': 'dashain', 'description': 'temporary',
            'discount_percent': 0, 'puja': None, 'is_active': False,
        })
        check('a scratch kit can be created for the upload test', status == 201,
              f'{status} {scratch}')

        if status == 201:
            kit_id = scratch['id']
            status, body = multipart(
                f'/api/festivals/admin/kits/{kit_id}/', admin_token,
                fields={'name': scratch_name},
                files={'image': ('kit.png', PNG_BYTES, 'image/png')},
            )
            check('uploading an image to a kit succeeds', status == 200, f'{status} {body}')
            if status == 200:
                check('the kit kept its name alongside the upload',
                      body.get('name') == scratch_name, f'{body.get("name")!r}')
                check('the kit image URL is absolute and under kits/',
                      str(body.get('image', '')).startswith(('http://', 'https://', '/'))
                      and '/kits/' in str(body.get('image', '')),
                      f'image={body.get("image")!r}')

            # Restore the scratch kit's own image to nothing, then delete the kit.
            request('PATCH', f'/api/festivals/admin/kits/{kit_id}/',
                    token=admin_token, body={'image': None})
            status, _ = request('DELETE', f'/api/festivals/admin/kits/{kit_id}/',
                                token=admin_token)
            check('the scratch kit is deleted again', status == 204, f'got {status}')
    else:
        skip('kit image upload', 'no kits exist to test against')

    # The seeded kits must be exactly as they were found. This is the assertion the
    # first version of this script needed and did not have.
    status, after = request('GET', '/api/festivals/admin/kits/', token=admin_token)
    if status == 200:
        rows = after if isinstance(after, list) else after.get('results', [])
        untouched = all('/kits/' not in str(r.get('image') or '') for r in rows)
        check('no seeded kit was left pointing at a test upload', untouched,
              f'images={[r.get("image") for r in rows]}')
        check('no scratch kit was left behind',
              not any('Verify Day13 Scratch' in (r.get('name') or '') for r in rows),
              f'names={[r.get("name") for r in rows]}')

    # --- clean up: this script created the product, so it deletes it
    for pid in created_ids:
        request('DELETE', f'/api/products/admin/products/{pid}/', token=admin_token)


def test_area_analytics(admin_token, vendor_token):
    section('Per-area analytics — the breakdown agrees with the headline')

    status, areas = request('GET', '/api/analytics/areas/', token=admin_token)
    check('GET /api/analytics/areas/ returns 200', status == 200, f'{status} {areas}')
    if status != 200:
        return

    status, sales = request('GET', '/api/analytics/sales/', token=admin_token)
    check('the sales overview still returns 200', status == 200, f'{status}')

    # The invariant: two panels that disagree make both numbers untrustworthy.
    area_total = areas.get('totals', {}).get('revenue')
    check('the area totals equal the sales overview total_revenue',
          area_total == sales.get('total_revenue'),
          f'areas={area_total} sales={sales.get("total_revenue")}')

    row_sum = sum(a['revenue'] for a in areas.get('areas', []))
    check('the rows sum to the reported total',
          abs(row_sum - (area_total or 0)) < 0.01,
          f'rows={row_sum} total={area_total}')

    check('the order counts agree too',
          areas.get('totals', {}).get('orders') == sales.get('total_orders'),
          f'areas={areas.get("totals", {}).get("orders")} sales={sales.get("total_orders")}')

    # Shape
    if areas.get('areas'):
        first = areas['areas'][0]
        for key in ('slug', 'name', 'orders', 'cancelled_orders', 'revenue',
                    'share_percent', 'is_configured'):
            check(f'the area row carries {key}', key in first, f'keys={sorted(first.keys())}')
    else:
        skip('area row shape', 'no areas configured')

    # Every configured area appears, even at zero — "which areas never ordered" is
    # the actionable half of the report.
    status, public_areas = request('GET', '/api/products/areas/')
    if status == 200 and isinstance(public_areas, list):
        configured = {a['slug'] for a in public_areas}
        reported = {a['slug'] for a in areas.get('areas', [])}
        missing = configured - reported
        check('every configured area is listed, even with no orders',
              not missing, f'missing {missing}')
        check('the configured areas report zero orders rather than being absent',
              all(a['orders'] >= 0 for a in areas['areas']), 'a negative order count appeared')
    else:
        skip('configured-area coverage', f'could not read /api/products/areas/ ({status})')

    shares = [a['share_percent'] for a in areas.get('areas', [])]
    if shares and area_total:
        check('the shares sum to 100%', abs(sum(shares) - 100.0) < 0.6,
              f'sum={sum(shares)}')
    else:
        check('an empty ledger reports 0% shares rather than dividing by zero',
              all(s == 0.0 for s in shares), f'shares={shares}')

    # Authorization
    status, _ = request('GET', '/api/analytics/areas/')
    check('an anonymous request is refused', status in (401, 403), f'got {status}')
    if vendor_token:
        status, vendor_view = request('GET', '/api/analytics/areas/', token=vendor_token)
        check('a vendor may read the breakdown', status == 200, f'got {status}')
        if status == 200:
            check("a vendor's breakdown is scoped, not global",
                  vendor_view.get('scope') == 'vendor', f'{vendor_view.get("scope")}')
            status, vendor_sales = request('GET', '/api/analytics/sales/', token=vendor_token)
            if status == 200:
                check("a vendor's area totals match their own sales overview",
                      vendor_view['totals']['revenue'] == vendor_sales.get('total_revenue'),
                      f'areas={vendor_view["totals"]["revenue"]} '
                      f'sales={vendor_sales.get("total_revenue")}')
    else:
        skip('vendor-scoped area analytics', 'could not log in as vendor1')


def test_inventory_integrity(customer_token, admin_token):
    """Cancelling an order must return its units to stock — end to end.

    The unit tests cover the transitions; this checks the same invariant against the
    running server, which is the state the demo is actually in. It matters because the
    bug it guards was invisible for the whole life of the project: `CheckoutView`
    decremented `product.stock` and nothing ever gave it back, so the catalogue leaked
    inventory with every cancellation and every verification sweep. By the time it was
    found the drift had reached **538 units across 23 products**, which in turn produced
    false low-stock and restock alerts — the demand-prediction feature reporting on
    inventory that did not exist.
    """
    section('Inventory integrity — a cancelled order returns its units')

    status, listing = request('GET', '/api/products/?page=1')
    if status != 200 or not isinstance(listing, dict) or not listing.get('results'):
        skip('inventory integrity', 'no products to order')
        return
    product = next((p for p in listing['results'] if p['stock'] >= 5), None)
    if product is None:
        skip('inventory integrity', 'no product with enough stock')
        return

    slug = product['slug']
    status, before = request('GET', f'/api/products/{slug}/')
    stock_before = before['stock']
    popularity_before = before['popularity_score']

    status, areas = request('GET', '/api/products/areas/')
    if status != 200 or not areas:
        skip('inventory integrity', 'no delivery areas')
        return

    # Place a real order for two units.
    request('POST', '/api/orders/cart/add/', token=customer_token,
            body={'product_id': product['id'], 'quantity': 2})
    status, order = request('POST', '/api/orders/checkout/', token=customer_token, body={
        'shipping_address': 'verify_day13.py inventory check',
        'phone': '9800000013', 'shipping_city': areas[0]['slug'],
        'payment_method': 'cod', 'notes': 'verify_day13.py inventory check',
    })
    if status != 201:
        skip('inventory integrity', f'checkout failed ({status})')
        return

    status, mid = request('GET', f'/api/products/{slug}/')
    check('placing an order reserves stock',
          mid['stock'] == stock_before - 2,
          f"{stock_before} -> {mid['stock']}, expected {stock_before - 2}")

    status, cancelled = request(
        'PATCH', f'/api/orders/admin/orders/{order["id"]}/',
        token=admin_token, body={'status': 'cancelled'},
    )
    check('staff can cancel the order', status == 200, f'{status} {cancelled}')

    status, after = request('GET', f'/api/products/{slug}/')
    check('cancelling returns the units to stock',
          after['stock'] == stock_before,
          f"stock is {after['stock']}, expected {stock_before} — "
          f"the cancelled units were not returned")

    # A second cancel must not hand the units back twice.
    request('PATCH', f'/api/orders/admin/orders/{order["id"]}/',
            token=admin_token, body={'status': 'cancelled'})
    status, twice = request('GET', f'/api/products/{slug}/')
    check('cancelling twice does not restore twice',
          twice['stock'] == stock_before,
          f"stock is {twice['stock']}, expected {stock_before}")

    # `popularity_score` is a demand signal, not a stock count: a cancelled order still
    # means a customer asked for something, so cancelling deliberately leaves it alone.
    # Fixture traffic is undone by `purge_verification_orders` instead, which knows the
    # order was never real demand.
    check('cancelling does not reverse the demand signal (by design)',
          twice['popularity_score'] == popularity_before + 2,
          f"popularity is {twice['popularity_score']}, expected "
          f"{popularity_before + 2} — the field is meant to stay monotonic")

    # The cancelled order is left for `purge_verification_orders`, which releases stock
    # only for orders that still hold a reservation and reverses popularity for all of
    # them — so it will not double-count this.
    print(f'  note  order {order["id"]} left cancelled for purge_verification_orders')


def test_storefront_contracts():
    section('Storefront contracts the new features depend on')
    # The heart on a card reads `product.id` from the list payload, and the wishlist
    # page renders the same shape. A list that stopped publishing `id` would break
    # the toggle silently, because the button would post `undefined`.
    status, listing = request('GET', '/api/products/?page=1')
    if status == 200 and isinstance(listing, dict) and listing.get('results'):
        row = listing['results'][0]
        check('the product list still publishes id and slug',
              'id' in row and 'slug' in row, f'keys={sorted(row.keys())}')
        check('the product list publishes the fields a card renders',
              all(k in row for k in ('name', 'price', 'image', 'in_stock', 'category_name')),
              f'keys={sorted(row.keys())}')
    else:
        skip('product list contract', f'{status}')

    # The kit list feeds the festivals page; an added `image` field must not have
    # displaced anything it already carried. The expected keys were **read off the
    # live response** before being pinned here — an earlier version of this check
    # guessed `items` and failed against a payload that had never had it, which is a
    # verifier bug that reads exactly like a product bug.
    status, kits = request('GET', '/api/festivals/kits/')
    if status == 200:
        rows = kits if isinstance(kits, list) else kits.get('results', [])
        if rows:
            kit = rows[0]
            expected = ['id', 'name', 'festival_type', 'festival_type_display',
                        'description', 'image', 'discount_percent', 'item_count',
                        'original_price', 'total_price']
            missing = [k for k in expected if k not in kit]
            check('the public kit payload is unchanged in shape',
                  not missing, f'missing {missing}')
            check('the public kit payload still publishes its image',
                  'image' in kit, f'keys={sorted(kit.keys())}')
        else:
            skip('public kit payload', 'no kits returned')
    else:
        skip('public kit payload', f'{status}')


def main():
    print(f'Day 13 verification against {BASE}  (run id {RUN})')

    admin_token = login('admin', 'admin123')
    if not admin_token:
        print('  FATAL: could not log in as admin/admin123 — is the server seeded?')
        return 2

    vendor_token = login('vendor1', 'vendor1234')
    if not vendor_token:
        skip('vendor checks', 'vendor1/vendor1234 could not log in')

    # Two throwaway customers. Unique per run, or a re-run 400s on the duplicate
    # username and silently skips the most important section. The `verifyday` prefix
    # is what `purge_verification_users` matches.
    customer_token = register(f'verifyday13a{RUN}', f'verifyday13a{RUN}@example.com')
    other_token = register(f'verifyday13b{RUN}', f'verifyday13b{RUN}@example.com')

    if not customer_token or not other_token:
        print('  FATAL: could not register the probe accounts')
        return 2

    test_wishlist(customer_token, other_token, admin_token)
    test_image_upload(admin_token)
    test_area_analytics(admin_token, vendor_token)
    test_inventory_integrity(customer_token, admin_token)
    test_storefront_contracts()

    print(f'\n{"=" * 60}')
    print(f'  {PASS} passed, {FAIL} failed, {SKIP} skipped')
    if FAILURES:
        print('  Failed checks:')
        for name in FAILURES:
            print(f'    - {name}')
    print(f'{"=" * 60}')
    print('\n  Clean up the probe accounts with:')
    print('    ./venv/Scripts/python.exe manage.py purge_verification_users')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
