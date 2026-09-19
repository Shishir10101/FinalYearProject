# API Specification

**Base URL:** `http://127.0.0.1:8000/api`
**Auth:** JWT bearer (`Authorization: Bearer <access>`)
**Format:** JSON

> **There is no session authentication on the API.** `djangorestframework-simplejwt`
> is the only configured authentication class. Django's `force_login()` therefore
> produces silent 401s in tests — bearer tokens are mandatory. This has bitten
> this project twice; see `AGENTS.md` §7.

---

## 0. Conventions

### Authentication header

```http
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### Status codes actually returned

| Code | Meaning in this API |
|---|---|
| `200` | OK |
| `201` | Created |
| `204` | Deleted (no body) |
| `400` | Validation error — body has per-field arrays |
| `401` | No token, or token expired |
| `403` | Authenticated but the role is insufficient |
| `404` | Not found — **also used for "exists but not yours"**, to avoid leaking existence |

### A note on 403 vs 404

Vendor scoping is applied in `get_queryset()`, not in a permission class. A
vendor requesting another vendor's product gets **404**, not 403, so they cannot
even confirm the product exists. Permission-class failures (a customer hitting an
admin route) return **403**.

### Pagination

List endpoints use `PageNumberPagination` with `PAGE_SIZE = 12`:

```json
{ "count": 35, "next": "http://.../products/?page=2", "previous": null, "results": [ ... ] }
```

Endpoints with `pagination_class = None` return a bare JSON array.
**Always check for `results`** — `len(response)` on a paginated body returns 4
(the number of keys), which is a silent bug.

---

## 1. Authentication — `/api/auth/`

| Method | Path | Auth | Description |
|---|---|---|---|
| `POST` | `/register/` | Public | Create a customer account |
| `POST` | `/login/` | Public | Obtain an access + refresh token pair |
| `POST` | `/token/refresh/` | Public | Exchange a refresh token for a new access token |
| `GET` | `/profile/` | Any | Current user + nested profile |
| `PUT` | `/profile/` | Any | Update own profile (partial allowed) |
| `POST` | `/password-reset/` | Public | Request a reset link *(Day 4)* |
| `POST` | `/password-reset/confirm/` | Public | Set a new password with uid + token *(Day 4)* |

### `POST /login/`

```json
{ "username": "admin", "password": "admin123" }
```

→ `200`

```json
{ "refresh": "...", "access": "..." }
```

Access token lifetime: 1 day. Refresh: 7 days, with rotation.

### `GET /profile/`

```json
{
  "id": 3,
  "username": "vendor1",
  "email": "",
  "first_name": "",
  "last_name": "",
  "profile": {
    "phone": "",
    "address": "",
    "city": "kathmandu",
    "role": "vendor",
    "is_admin_user": false
  }
}
```

**`profile.role` is read-only.** `PATCH`/`PUT` silently ignore any attempt to
change it — verified by `core/tests_roles.py::RoleEscalationTests`.

**Role values:** `super_admin` · `admin` · `vendor` · `customer`

### `POST /password-reset/`

```json
{ "email": "test@example.com" }
```

→ `200` — **the same response whether or not the address has an account:**

```json
{ "message": "If an account exists for that email address, a password reset link has been sent. Please check your inbox." }
```

With `PASSWORD_RESET_EXPOSE_LINK` on (it defaults to `DEBUG`) two extra fields are
added so the flow can be demonstrated without a mailbox:

```json
{
  "message": "…",
  "reset_url": "http://localhost:3000/auth/reset-password?uid=Mg&token=…",
  "dev_note": "Development build only: this link is returned in the response because no mailbox is configured. It is never returned when PASSWORD_RESET_EXPOSE_LINK is off."
}
```

> ⚠️ Returning the link **is** account enumeration — a link can only exist for a
> real account. That is why it is a flag, why it is asserted to leak exactly those
> two fields and nothing else, and why the production configuration
> (`PASSWORD_RESET_EXPOSE_LINK = False`) is separately asserted to be
> byte-identical for known and unknown addresses. **Never enable it in a real
> deployment.**

Rate limited to 10/min per IP (`password_reset` throttle scope). A mail delivery
failure is logged, not surfaced — a 500 only happens when an account matched,
which would leak the same fact the generic message protects.

### `POST /password-reset/confirm/`

```json
{
  "uid": "Mg",
  "token": "df5wtr-b562b98ad637fd880fa8a3e27f46d2c1",
  "new_password": "BrandNewPass456",
  "new_password2": "BrandNewPass456"
}
```

→ `200`

```json
{ "message": "Your password has been reset. You can now sign in with your new password." }
```

→ `400` — field-keyed, and deliberately identical for a bad uid and a bad token:

```json
{ "token": ["This reset link is invalid or has expired. Please request a new one."] }
```

Other `400` shapes: `{"new_password2": ["The two passwords do not match."]}` and
`{"new_password": ["This password is too short. It must contain at least 8 characters."]}`
(the new password runs through Django's `AUTH_PASSWORD_VALIDATORS`).

**A link works exactly once.** The token hash includes the password hash and
`last_login`, so using it — or logging in in the meantime — invalidates it. No
token is stored server-side and no cleanup job is needed.

**Known limitation:** existing JWTs are not revoked by a reset. Access tokens are
stateless and last 1 day.

---

## 2. Catalogue — `/api/products/`

### Public

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Paginated product list. Filters: `?category=<id>&search=<q>&ordering=price` |
| `GET` | `/<slug>/` | Product detail, includes `vendor` summary |
| `GET` | `/featured/` | Featured products |
| `GET` | `/categories/` | All categories |
| `GET` | `/categories/<slug>/` | Products in a category |
| `GET` | `/areas/` | **Delivery areas** (added Day 3) — canonical JSON array |

`GET /areas/` →

```json
[
  { "id": 1, "name": "Kathmandu", "slug": "kathmandu", "district": "Kathmandu",
    "delivery_fee": null, "is_active": true },
  { "id": 2, "name": "Lalitpur", "slug": "lalitpur", "district": "Lalitpur",
    "delivery_fee": null, "is_active": true },
  { "id": 3, "name": "Bhaktapur", "slug": "bhaktapur", "district": "Bhaktapur",
    "delivery_fee": null, "is_active": true }
]
```

`delivery_fee: null` means "use the store-wide default" (`/orders/config/`).

### Admin — vendor-scoped

| Method | Path | Required role | Notes |
|---|---|---|---|
| `GET` | `/admin/products/` | any staff | Vendors see **only their own**; managers see all |
| `POST` | `/admin/products/` | any staff | A vendor's product is force-attributed to them |
| `GET` | `/admin/products/<id>/` | any staff | 404 if not yours |
| `PATCH` | `/admin/products/<id>/` | any staff | 404 if not yours |
| `DELETE` | `/admin/products/<id>/` | any staff | 404 if not yours |
| `GET`/`POST` | `/admin/categories/` | read: any staff · write: **manager** | Vendors may read the taxonomy |
| `GET`/`PATCH`/`DELETE` | `/admin/categories/<id>/` | read: any staff · write: **manager** | |
| `GET`/`POST` | `/admin/areas/` | read: **manager** · write: **manager** | |
| `GET`/`PATCH`/`DELETE` | `/admin/areas/<id>/` | **manager** | |
| `GET`/`POST` | `/admin/vendors/` | read: any staff (vendors see only self) · write: **manager** | |
| `GET`/`PATCH`/`DELETE` | `/admin/vendors/<id>/` | read: any staff (vendors see only self) · write: **manager** | |

**Product create payload**

```json
{
  "name": "Pashupatinath Puja Thali",
  "description": "Complete thali for Monday Shiva puja.",
  "price": "450.00",
  "stock": 25,
  "category": 3,
  "vendor": 1,
  "unit": "piece",
  "is_featured": false,
  "is_active": true
}
```

`name` is required — `""` returns `400`. `category` must be a real id.
`slug`, `created_at`, `updated_at` are read-only.

> **Spoofing guard.** A vendor sending `"vendor": <someone-else-id>` gets the
> product assigned to **their own** vendor row. Only a manager can assign an
> arbitrary vendor. Covered by `test_vendor_created_product_is_attributed_to_them`.

---

## 3. Cart, checkout and orders — `/api/orders/`

### Public

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/config/` | Public | Store configuration |

`GET /config/` →

```json
{ "delivery_fee": 100, "free_delivery_threshold": null, "currency": "NPR" }
```

Delivery areas are **not** in this payload — fetch them from `GET /products/areas/`.
`free_delivery_threshold` is `null`, meaning "no free-delivery offer"; the field
exists so the storefront does not need a code change to add one.

**Why this endpoint exists.** On Day 1 the delivery fee lived in three places
(frontend constant, backend default, and nowhere in the stored order), and order
#9 recorded Rs. 290 while the UI promised Rs. 390. The fee is now served from a
single setting and stored on the order.

### Cart — authenticated

| Method | Path | Description |
|---|---|---|
| `GET` | `/cart/` | Current user's cart with computed totals |
| `POST` | `/cart/add/` | `{ "product": <id>, "quantity": 1 }` |
| `PATCH` | `/cart/update/<id>/` | `{ "quantity": 3 }` |
| `DELETE` | `/cart/remove/<id>/` | Remove a line |
| `POST` | `/cart/add-kit/<kit_id>/` | Add every item in a festival kit at once |
| `POST` | `/cart/add-puja/<puja_id>/` | Add a ritual's **essential** items *(added Day 6)* |

### `POST /cart/add-puja/<puja_id>/`

Mirrors `add-kit`, but driven by the ritual's own item list rather than a kit's —
which is the point of Puja being a separate entry point: you can shop by ceremony
even when no kit exists for it.

```json
{ "message": "6 items added to cart for \"Dashain Tika\"", "added": 6 }
```

Anything that could not be added is **reported**, never silently dropped:

```json
{
  "message": "4 items added to cart for \"Dashain Tika\"",
  "added": 4,
  "skipped": ["Brass Diyo (Oil Lamp)", "Mustard Oil for Diyo (500ml)"],
  "warning": "Some items could not be added because they are out of stock: …"
}
```

**Only required items are added.** Optional extras are a merchandising choice, and
putting them in the cart on the customer's behalf would be putting words in their
mouth. Unknown or inactive ritual → **404**. No token → **401**.

### Checkout and history

| Method | Path | Description |
|---|---|---|
| `POST` | `/checkout/` | Create an order from the cart |
| `GET` | `/` | Own order history (paginated) |
| `GET` | `/<id>/` | Own order detail |

`POST /checkout/` body:

```json
{
  "shipping_address": "Thamel, Kathmandu",
  "shipping_city": "kathmandu",
  "phone": "9800000000",
  "notes": "",
  "payment_method": "cod"
}
```

Wrapped in `transaction.atomic`: each product's stock is re-checked and
decremented, and insufficient stock raises `400` rather than overselling.

Checkout also opens the order's status history with a `pending` event. A mocked
`esewa`/`khalti` payment adds a second `pending → confirmed` event.

### `timeline` — the order status tracker *(timestamps added Day 4)*

Every order payload (`/`, `/<id>/`, and the admin list) carries a `timeline`
object:

```json
{
  "steps": [
    { "key": "pending",    "label": "Order Placed",     "state": "done",    "at": "2026-09-19T17:04:11.482Z" },
    { "key": "confirmed",  "label": "Confirmed",        "state": "done",    "at": "2026-09-19T17:04:12.117Z" },
    { "key": "processing", "label": "Preparing",        "state": "current", "at": "2026-09-19T17:06:40.009Z" },
    { "key": "shipped",    "label": "Out for Delivery", "state": "upcoming","at": null },
    { "key": "delivered",  "label": "Delivered",        "state": "upcoming","at": null }
  ],
  "current": "processing",
  "is_terminal": false,
  "history": [
    { "status": "pending",    "label": "Pending",    "at": "2026-09-19T17:04:11.482Z" },
    { "status": "confirmed",  "label": "Confirmed",  "at": "2026-09-19T17:04:12.117Z" },
    { "status": "processing", "label": "Processing", "at": "2026-09-19T17:06:40.009Z" }
  ]
}
```

- `state` is one of `done` · `current` · `upcoming` · `cancelled`.
- `at` comes from a real `OrderStatusEvent` row, or is **`null`** when the step has
  no recorded event. `null` is rendered as "not recorded" — it is never
  back-filled with a plausible-looking time. Orders placed before Day 4 have a
  single backfilled event, so their earlier steps are legitimately undated.
  `pending` falls back to `Order.created_at`, because an order *was* necessarily
  placed at that moment.
- A `delivered` order is terminal and its last step is `done`, not `current` —
  otherwise a completed order looks permanently in progress.
- `cancelled` does not fit a linear progression, so it returns its own two-step
  timeline (`pending` + `cancelled`) with `is_terminal: true`.
- `history` carries **no** note text and **no** staff identity. It is a
  customer-facing progress list, not a staff audit log.

### Admin — vendor-scoped

| Method | Path | Required | Notes |
|---|---|---|---|
| `GET` | `/admin/orders/` | any staff | Vendors see only orders containing **their** products |
| `PATCH` | `/admin/orders/<id>/` | any staff | `{ "status": "shipped" }` — 404 if the order has none of your products |

An order containing two of a vendor's products appears **once** (`.distinct()`).

---

## 4. Festivals, kits and recommendations — `/api/festivals/`

| Method | Path | Auth | Description |
|---|---|---|---|
| `GET` | `/kits/` | Public | Festival kits |
| `GET` | `/kits/<id>/` | Public | Kit detail with items and computed price |
| `GET` | `/upcoming/` | Public | Festivals from today forward. `?limit=` (default 5, max 50) |
| `GET` | `/pujas/` | Public | **Rituals** — the fourth discovery entry point |
| `GET` | `/pujas/<slug>/` | Public | One ritual with the samagri it calls for |
| `GET` | `/recommendations/` | Public | **Ranked, explainable recommendations** |

### `GET /pujas/` and `GET /pujas/<slug>/` *(added Day 6)*

`AGENTS.md` §1 requires discovery through six entry points — Product · Category ·
Festival · **Puja** · Samagri · Ready-made Kit. The Puja one had no model,
endpoint or page; `festival_type` was doing double duty for calendar festivals
*and* rites of passage.

Not paginated — the ritual list is short and renders as a single grid.

```json
[
  {
    "id": 2,
    "name": "Dashain Tika",
    "slug": "dashain-tika",
    "description": "Everything you need for Dashain puja — tika, garlands, diyo, and offerings. …",
    "occasion_type": "dashain",
    "occasion_display": "Dashain",
    "item_count": 8,
    "required_count": 6,
    "kit_id": 1,
    "kit_name": "Dashain Puja Complete Kit"
  },
  {
    "id": 1,
    "name": "Daily Puja",
    "slug": "daily-puja",
    "occasion_type": "other",
    "item_count": 21,
    "required_count": 21,
    "kit_id": null,
    "kit_name": null
  }
]
```

`kit_id` is `null` when no ready-made kit exists — which is the normal state, not
an error. The six entry points name Puja and Ready-made Kit **separately**, so a
ritual must be usable without one.

`GET /pujas/<slug>/` adds `items[]` (with `product_detail`, `quantity`,
`is_required`) and a nested `kit` object when one exists:

```json
{
  "id": 2, "name": "Dashain Tika", "slug": "dashain-tika",
  "occasion_type": "dashain", "occasion_display": "Dashain",
  "items": [
    { "id": 9, "product": 5, "quantity": 2, "is_required": true,
      "product_detail": { "id": 5, "name": "Sindoor Powder (Red)", "price": "50.00", … } }
  ],
  "kit": { "id": 1, "name": "Dashain Puja Complete Kit", "total_price": "1152.00", … }
}
```

Items come back **essentials first** (ordering `('-is_required', 'id')`).
`item_count` / `required_count` are queryset annotations, not per-row counts.

Unknown slug → **404**. Inactive ritual → **404**. Both are asserted live.

> **Frontend note.** `/pujas` and `/pujas/[slug]` are Server Components, so an
> unknown slug renders the styled 404 with a **200** status when the response has
> already started streaming — Next's documented behaviour. It injects
> `<meta name="robots" content="noindex">` as the mitigation. The RSC payload still
> carries `NEXT_HTTP_ERROR_FALLBACK;404`.

### `GET /upcoming/`

Soonest first. The result count used to be a hardcoded `[:5]`, so five of the ten
active future festivals were unreachable through the API and nothing said so —
the storefront and the home page both silently showed the first five. It is now a
parameter:

| Query | Result |
|---|---|
| *(none)* | 5 — preserves the previous default |
| `?limit=12` | up to 12 |
| `?limit=9999` | capped at 50 |
| `?limit=0` | floored at 1 |
| `?limit=abc` | falls back to the default 5 |

Past festivals are never returned, whatever the limit.

### `GET /recommendations/`

```json
{
  "festival_context": { "name": "Dashain", "days_until": 18, "date": "2026-10-06" },
  "meta": {
    "window_days": 45,
    "signals": ["festival_required", "user_category", "popularity", "..."],
    "model": "festivals.recommender.Recommender v1",
    "explanation": "Ranked by upcoming festival requirements, your past orders, and catalogue popularity."
  },
  "results": [
    {
      "id": 21,
      "name": "Janai (Sacred Thread)",
      "price": "45.00",
      "recommendation": {
        "score": 90.0,
        "urgency": "required",
        "urgency_label": "Required for Dashain",
        "reason": {
          "code": "festival_required",
          "text": "Required for Dashain in 18 days — marked essential in that festival kit."
        }
      }
    }
  ]
}
```

**Every item carries a `reason`.** There is no random-product path. See
`docs/AI-RECOMMENDATION.md` for the weight table and worked examples.

### Admin kits

| Method | Path | Required |
|---|---|---|
| `GET`/`POST` | `/admin/kits/` | read: any staff · write: **manager** |
| `GET`/`PATCH`/`DELETE` | `/admin/kits/<id>/` | read: any staff · write: **manager** |
| `GET`/`POST` | `/admin/kits/<kit_id>/items/` | read: any staff · write: **manager** |
| `DELETE` | `/admin/kit-items/<id>/` | **manager** |

---

## 5. Analytics — `/api/analytics/`

All endpoints require a staff role. Vendor results are scoped to their own
products and carry `"scope": "vendor"`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/sales/` | Revenue, order counts, 30-day daily series |
| `GET` | `/trending/` | Top products by popularity |
| `GET` | `/inventory/` | Stock levels, low-stock and out-of-stock lists |
| `GET` | `/predictions/` | Actionable alerts (festival, inventory, forecast) |
| `GET` | `/demand-forecast/` | **Per-product demand forecast** |

### `GET /sales/`

```json
{
  "total_orders": 8,
  "total_revenue": 8420.0,
  "revenue_30d": 8420.0,
  "orders_30d": 8,
  "revenue_7d": 2100.0,
  "orders_7d": 2,
  "total_products": 35,
  "scope": "all",
  "status_counts": { "pending": 5, "delivered": 3 },
  "daily_data": [ { "date": "2026-08-20", "revenue": 0.0, "orders": 0 } ]
}
```

`scope` is `"all"` for managers, `"vendor"` for vendors.

### `GET /demand-forecast/`

Query params: `?horizon=30` (1–90) · `?limit=12` (1–50) · `?product=<id>`

```json
{
  "data_source": "synthetic",
  "is_synthetic": true,
  "provenance_note": "SYNTHETIC DATA: this forecast is fitted on a generated dataset...",
  "horizon_days": 30,
  "generated_at": "2026-09-18T...",
  "forecasts": [
    {
      "product": { "id": 1, "name": "Premium Dhoop Batti", "category": "...",
                   "price": 120.0, "stock": 50 },
      "forecast_total_units": 34.2,
      "avg_daily_units": 1.14,
      "stock_cover_days": 43.9,
      "restock_needed": false,
      "projected_shortfall": 0,
      "metrics": { "mape": 26.2, "mae": 0.81, "rmse": 1.04, "naive_mae": 0.936 },
      "components": { "weekday_factors": { ... }, "trend": 0.02 },
      "predictions": [ { "date": "2026-09-19", "units": 1.4 } ]
    }
  ],
  "aggregate": {
    "total_forecast_units": 412.6,
    "products_covered": 35,
    "products_needing_restock": 24,
    "mean_mape": 26.2
  },
  "model": { "name": "seasonal-trend-festival", "version": 1 }
}
```

> ### ⚠️ `is_synthetic` is always `true` for this endpoint
>
> The model is fitted on generated data, not real orders. The response says so
> explicitly and in every derived cache. A caller requesting another vendor's
> product gets `404`.

---

## 6. Role → endpoint matrix

| Endpoint group | customer | vendor | admin | super_admin |
|---|---|---|---|---|
| Public catalogue, kits, areas, recommendations | ✅ | ✅ | ✅ | ✅ |
| Own cart / checkout / own orders | ✅ | ✅ | ✅ | ✅ |
| `/analytics/*` | ❌ 403 | ✅ *scoped* | ✅ | ✅ |
| `/products/admin/products/*` | ❌ 403 | ✅ *scoped* | ✅ | ✅ |
| `/orders/admin/orders/*` | ❌ 403 | ✅ *scoped* | ✅ | ✅ |
| `/products/admin/categories/*` (read) | ❌ 403 | ✅ | ✅ | ✅ |
| `/products/admin/categories/*` (write) | ❌ 403 | ❌ 403 | ✅ | ✅ |
| `/products/admin/areas/*` | ❌ 403 | ❌ 403 | ✅ | ✅ |
| `/products/admin/vendors/*` (read) | ❌ 403 | ✅ *self only* | ✅ | ✅ |
| `/products/admin/vendors/*` (write) | ❌ 403 | ❌ 403 | ✅ | ✅ |
| `/festivals/admin/*` (write) | ❌ 403 | ❌ 403 | ✅ | ✅ |

Verified end-to-end by `backend/verify_day3.py` (55 assertions) and
`backend/core/tests_roles.py` (47 unit tests).

---

## 7. Error response shape

Field validation (`400`):

```json
{ "name": ["This field may not be blank."], "price": ["Ensure that there are no more than 10 digits in total."] }
```

Permission (`403`):

```json
{ "detail": "You do not have permission to perform this action." }
```

The admin dashboard's API client extracts `.detail`, `.error`, or
`.non_field_errors[0]` and shows it to the user — never a stack trace.
