# CURRENT-STATE.md

Analysis date: 2026-09-18
Method: full source inspection + live server probing.
Last updated: 2026-09-19 (Day 4 complete — see §Day 4 Completed below).

---

## Day 4 Completed (2026-09-19) — trust & honesty pass

**Theme:** close the gaps the documentation itself admitted to, and fix the bugs
found while doing it. No new headline features; this pass is about the existing
ones being *true*.

**Verification: 380 live assertions + 178 backend unit tests, all passing.**

| # | Was | Now |
|---|-----|-----|
| 1 | The order timeline was **derived** from `Order.status`, so every step was permanently undated — it could say where an order was, never when it got there | **FIXED** — new append-only `OrderStatusEvent` table. Checkout and every admin status change append a row; `timeline.steps[].at` now carries a real timestamp. 23 unit tests. |
| 2 | Password reset **did not exist** (B9, required by the brief) | **BUILT** — real `PasswordResetTokenGenerator` flow at `POST /api/auth/password-reset/` + `/confirm/`, two storefront pages, throttled. 25 unit tests. |
| 3 | Admin modals showed one general banner; the per-field markup was dead code | **FIXED** — per-field errors populate from the DRF body, plus a safety net so no error can render invisibly. |
| 4 | *(found while fixing #3)* **`Catalog Settings` was completely broken** — 4 undefined `setFieldError` calls | **FIXED** — every New/Edit button threw `ReferenceError` before opening its dialog. |
| 5 | *(found while probing error shapes)* Negative price, negative delivery fee and duplicate category names were all **accepted** | **FIXED** — rejected with a field-level error. |
| 6 | Every byte of Day 1–3 work was **uncommitted**; `backend/` and the root were not git repos at all | **FIXED** — root repo created (`backend`, `docs`, `AGENTS.md`, `README.md`), both frontends committed. A rollback path now exists. |

### 1. Real order status history

`OrderStatusEvent` (`orders/models.py`) records `from_status → to_status`, a note,
who changed it, and when. Written from the two places a status can move:
`CheckoutView` (the initial `pending`, plus `confirmed` for a mocked wallet
payment) and `AdminOrderUpdateView.perform_update()`.

Three details that matter:

- `created_at` uses `default=timezone.now`, **not** `auto_now_add`. The latter
  silently discards any value passed to it, so the backfill migration for the
  eight pre-existing orders could not have preserved their real `created_at`.
  Locked down by `test_explicit_timestamp_is_preserved`.
- The event is written **only for a genuine transition**. Re-saving the same
  status, or changing only `payment_status`, adds nothing — otherwise the
  customer's timeline fills with meaningless duplicate steps.
- `at` is `null` for a step with no recorded event, and the UI says
  "not recorded". The eight seeded orders each have one backfilled event, so
  their earlier steps are legitimately undated. Borrowing `created_at` for them
  would be inventing a delivery date. `pending` is the one honest exception: an
  order *was* necessarily placed at `Order.created_at`.

### 2. Password reset

Django's own token generator, so two security properties come for free: the token
hash includes the password hash and `last_login`, which means a link stops working
the moment it is used, and also stops working if the account owner logs in first.

- `POST /api/auth/password-reset/` — always the same 200 and the same wording,
  whether or not the address has an account. A mail failure is **logged, not
  surfaced**, because a 500 only ever happens when an account matched, which
  would leak exactly what the generic message hides.
- `POST /api/auth/password-reset/confirm/` — validates uid + token, runs the new
  password through Django's `AUTH_PASSWORD_VALIDATORS` (so a reset cannot set a
  password that registration would have refused), then sets it.
- Both endpoints are throttled (`password_reset`, 10/min).
- A bad uid and a bad token return byte-identical responses, asserted by
  `test_bad_uid_and_bad_token_are_indistinguishable`.
- New storefront pages `/auth/forgot-password` and `/auth/reset-password`, plus a
  "Forgot password?" link on the login form.

**Two honest caveats, recorded rather than hidden:**

1. **`PASSWORD_RESET_EXPOSE_LINK` (`= DEBUG`) returns the reset link in the JSON
   response.** It exists so the flow can be demonstrated without a mailbox — the
   console email backend prints the message to the `runserver` terminal. It is
   account-enumeration by design, so it is asserted explicitly
   (`test_dev_exposure_leaks_exactly_two_fields_and_nothing_else`) and the
   production configuration is asserted separately to be byte-identical for
   known and unknown addresses. **It must be `False` in any real deployment.**
2. **Existing JWTs survive a password reset.** Access tokens are stateless and
   last a day, so a stolen token keeps working until it expires. Real revocation
   needs a blacklist or a per-user token version — deliberately out of scope.

### 3. Admin dashboard validation

- `fieldErrors()` in `admin-dashboard/src/lib/api.js` now joins **all** messages
  per field instead of keeping only the first, and guarantees a `_general`
  fallback so an error response can never render as an empty dialog.
- `products/page.js` had its own weaker copy of that helper, which dropped
  `non_field_errors`/`detail` into keys nothing rendered — a cross-field
  rejection would have failed **silently**. It now imports the shared one.
- The products modal's catch block always set `_general`, so the per-field spans
  next to each input were unreachable. Both modals now show per-field messages
  and have a safety net for any field with no input on screen.

### 4. `Catalog Settings` was broken, and lint did not catch it

Four calls to a bare `setFieldError({})` — the state setter lives inside the
`useCrud` hook and is only reachable as `c.setFieldError`. Every "+ New Category",
"Edit", "+ New Area" and "Edit" button threw `ReferenceError` before its dialog
could open.

The project's ESLint config does not enable `no-undef`, so `next lint` was clean.
Turning it on finds it immediately, and confirms these four were the only ones:

```
npx eslint --rule '{"no-undef":"error"}' src/
  166:5  error  'setFieldError' is not defined  no-undef
  172:5  error  'setFieldError' is not defined  no-undef
  302:5  error  'setFieldError' is not defined  no-undef
  313:5  error  'setFieldError' is not defined  no-undef
```

That command is now the documented way to catch this class of bug.

### 5. Three data-integrity holes

Found by probing the live API for the real error *shapes* the dashboard would
have to render. All three were accepted:

| Payload | Consequence |
|---|---|
| `price: -5` | Subtracts from the cart total |
| `delivery_fee: -50` on an `Area` | The store pays the customer to deliver |
| Duplicate category name | Filed as `puja-oils-ghee-1` — one category becomes two, and the storefront shows both |

Fixed with `MinValueValidator(0)` on `Product.price` and `Area.delivery_fee`
(migration `products/0004`) — DRF copies model validators onto serializer fields,
so this covers the API and the Django admin — plus a case-insensitive name check
on `CategoryAdminSerializer`.

`Category.save()`'s slug suffixer **stays**. It exists because a duplicate slug
raised an unhandled `IntegrityError` (HTTP 500). The name check is what stops
duplicates happening; the suffixer remains the last-resort safety net for paths
the check cannot cover, such as two Devanagari names that slugify identically.

### Verification after Day 4

| Suite | Result |
|---|---|
| `manage.py test` | **178 pass** (was 136) |
| `verify_day4.py` | **88/88** |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | 55/55 — no regression |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| **Live assertions** | **380** |

- Both frontends build clean: frontend 13/13 routes (was 11 — the two new auth
  pages), admin 10/10.
- Authorization **not weakened**: customer 403 on all 10 admin surfaces, admin 200
  on all 10.
- Database restored to seeded state after the sweep: 3 users · 35 products
  (12 vendor-assigned) · 10 categories · 3 areas · 1 vendor · 8 orders · 20 order
  items · 0 cart lines · 7 kits · 10 active future festivals · 13,600 synthetic
  rows · **8 status events (the backfill)** · 0 scratch rows.
- All three demo logins verified working.

### New commands

| Command | Purpose |
|---|---|
| `manage.py purge_verification_users` | Removes verifier accounts by username prefix. `--dry-run` supported. |
| `manage.py purge_verification_orders` | Extended with the `verify_day4.py` marker and the Day-4 scratch address. |

### Docs updated

`CURRENT-STATE.md` (this section), `FEATURES.md` (§6 rewritten — three rows moved
out of "not built"), `DATABASE-DESIGN.md` (§3.3 `OrderStatusEvent`, §4 migration
history), `API-SPEC.md` (auth endpoints + timeline shape), `DEVELOPMENT-ROADMAP.md`
(Day 4 ✅), `AGENTS.md` (§3 model facts, §5 commands, §12 lint), `README.md`.

---

## Day 2 Completed (2026-09-18)

Both AI features are built, tested and surfaced in the UI.
Verification: **56 backend unit tests + 68 live E2E assertions, all passing.**

| # | Was | Now |
|---|-----|-----|
| B5 | Recommendations were an **unranked `set()`**, no explanation, no scoring | **FIXED** — `festivals/recommender.py::Recommender`: weighted additive ranker (7 signals), fully deterministic ordering, per-product `reasons[]` with `code`/`points`/`text`. 23 unit tests. |
| B6 | Demand prediction did not exist | **BUILT** — `analytics/forecasting.py::SeasonalForecaster` (dependency-free multiplicative decomposition), served at `GET /api/analytics/demand-forecast/`, admin UI at `/forecast`. 33 tests. |
| **NEW** | **All 5 `UpcomingFestival` rows were in the past** — the festival signal was dead and `/festivals/upcoming/` returned `[]`, silently reducing recommendations to "popular products" | **FIXED** — new idempotent `python manage.py refresh_festivals` command; 10 realistic future festivals seeded, 5 stale rows deactivated (not deleted). |

### Evidence the recommendation engine is real

Every score is decomposable into the reasons shown to the user — asserted by
`test_score_equals_sum_of_reason_points` for all products. Live example:

```
Premium Dhoop Batti (Pack of 20)              score = 198
   +60  [festival_required]  Required for Ghatasthapana (Dashain Begins) (33 days away)
   +60  [festival_required]  Required for Vijaya Dashami (43 days away)
   +28  [staple_samagri]     Everyday puja essential — needed for Ganesh Chaturthi in 6 days
   +16  [user_kit_affinity]  Goes with items you have bought before
   +22  [user_category]      You often buy from Dhoop & Agarbatti
   +12  [popular]            Popular item (score 89)
```

### Evidence the forecast model is real (not a fake)

It independently **recovered structure it was never told about**:

| Day | Generator's hidden truth | Model learned | |
|---|---|---|---|
| Tuesday | 0.90 | **0.842** | lowest ✓ |
| Friday | 1.15 | **1.094** | 2nd highest ✓ |
| Saturday | 1.30 | **1.191** | highest ✓ |

28-day **out-of-sample holdout**: mean MAPE **26.20 %**, MAE **0.810** vs naive baseline
**0.936** → **+13.5 % better than naive**. Reported as mediocre rather than inflated.

### Data provenance — stated plainly

The forecasting dataset is **synthetic** (14,000 rows / 35 products / 400 days,
fixed seed). Real data was 8 orders across 9 days — insufficient to train anything.
The synthetic flag is enforced at three levels: the row (`is_synthetic=True`), the API
(`data_source`, `is_synthetic`, `provenance_note`) and the UI (warning banner).
Tests assert all three. **No response presents synthetic data as real demand.**

**Verified after Day 2:**
- `manage.py check` clean · both frontends build exit 0 · all 15 pages render 200
- 18/18 authorization checks: customer 403 / admin 200 on every admin endpoint
  (new `/demand-forecast/` and `/predictions/` included — **authorization not weakened**)
- Recommendations: 8/8 rendered products carry an explanation; ordering stable across requests
- Forecast: horizon clamped 1–90, non-integer `product` → 400, predictions non-negative
- Home page now renders the repaired festival calendar + real featured products
- Day-1 guarantees re-verified (delivery fee single source of truth, auth, cart flow)

**Schema changes:** `analytics.SyntheticSalesRecord` created (migration `analytics/0001`) —
the app previously had **no models at all**. Additive only; no existing table touched.

---

## Day 3 Completed (2026-09-18)

**Theme:** make the role hierarchy real, and let an admin actually write to the catalogue.

Before Day 3 there was **no vendor role**. Authorization was a single binary:
DRF's `IsAdminUser`, which tests `is_staff`. `UserProfile.is_admin_user` existed,
was set by the seeder, was returned by the API, and was read by **no permission
check anywhere**. It was decorative.

### What was built

| # | Feature | Detail |
|---|---|---|
| 1 | **Role system** | `core/permissions.py` — four roles (`super_admin`/`admin`/`vendor`/`customer`), one resolver (`get_role`), 4 permission classes, 6 helpers |
| 2 | **`Area` model** | Replaced the `CITY_CHOICES` enum that was duplicated in `accounts` **and** `orders`. Seeded at byte-identical slugs so existing order data still resolves |
| 3 | **`Vendor` model** | 1:1 with `User`. This link is what makes ownership enforceable |
| 4 | **`Product.vendor`** | Nullable FK, `SET_NULL`. 12 of 35 products assigned to the demo vendor; 23 deliberately left unassigned |
| 5 | **Vendor scoping** | Products, orders, analytics, inventory, trending, alerts and forecast all filter by `vendor_for(request.user)` |
| 6 | **Admin CRUD** | Products (create/edit/delete/enable-disable), Categories, Areas — real write paths in the dashboard |
| 7 | **Role-aware UI** | Sidebar filters manager-only items; `/settings` renders an explanatory panel for vendors instead of a broken table |

### Two real bugs found and fixed

**Bug 1 — `get_role()` precedence granted vendors full admin access.**
The resolver checked `is_staff` *before* the explicit `profile.role`. A vendor
account is necessarily `is_staff` (it must reach the API at all), so `vendor1`
resolved to **`admin`**. The bug was silent: nothing errored, the vendor simply
saw the entire catalogue. Fixed by reordering to
`is_superuser → explicit profile.role → is_staff → customer`.
Locked down by `RoleResolutionTests::test_vendor_resolves_to_vendor_not_admin`.

**Bug 2 — a data migration silently did nothing.**
`products/migrations/0003` set the vendor's role with:

```python
UserProfile.objects.filter(user=vendor_user).update(role=ROLE_VENDOR)
```

`vendor1` had **no `UserProfile` row at all** (3 users, 2 profiles existed). A
`QuerySet.update()` against a non-matching filter returns `0` and raises nothing.
Without a profile, `get_role()` fell through to the `is_staff` fallback — **admin
again**, defeating the fix for Bug 1. Repaired by
`accounts/migrations/0003_backfill_missing_profiles.py`, which uses
`get_or_create` and asserts the result.

> Both bugs compounded: fixing the precedence alone would *still* have left
> `vendor1` as an admin. Neither was visible without asserting on observable
> behaviour rather than on the helper's return value.

### Third finding — inconsistent vendor views

`AdminVendorListCreateView` used `IsStaffRole` while `AdminVendorDetailView` used
`IsSuperAdmin`. An ADMIN could browse vendors and then get a **403 on every single
one** — a broken UI flow that no test covered. Both now share
`IsManagerOrReadOnly`.

### Fourth finding — `role` was missing from the profile API

The dashboard needs `role` to decide which UI to render. `UserProfileSerializer`
did not expose it. Added as **read-only** (a writable `role` would let any customer
PATCH themselves into a super admin).

**Verified after Day 3:**
- `manage.py check` clean · both frontends build exit 0 · `/settings` route created
- **101 unit tests** pass (was 56) — 47 new, covering roles and scoping
- **`verify_day3.py`: 55/55 live assertions** pass
- `verify_day2.py` 68 assertions still pass — **no regression**
- Authorization **not weakened**: customer → admin endpoint is still 403 (now on
  more endpoints than before, and vendor is confined to 12 of 35 products)
- Data integrity preserved: 35 products · 10 categories · 3 areas · 1 vendor ·
  8 orders · 20 order items · 7 kits. CRUD tests clean up after themselves.

**Schema changes (all additive):**

| Migration | Effect |
|---|---|
| `products/0002_area_vendor_product_vendor` | 2 new tables + 1 nullable FK |
| `accounts/0002_userprofile_role_*` | 1 new column + index |
| `products/0003_seed_areas_and_vendor` | Data: 3 areas, role backfill, demo vendor, 12 products |
| `accounts/0003_backfill_missing_profiles` | Data repair: profiles for users that had none |

No column dropped, no table renamed, no existing row rewritten destructively.

---

## Day 3.4 Completed (2026-09-18) — responsive sweep, E2E pass, 3 more bugs

### The most user-visible defect in the project
**`ProductDetailView` was never routed.** The view existed with
`lookup_field = 'slug'`, `ProductListSerializer` published a `slug`, and the customer
page called `/api/products/<slug>/` — but `products/urls.py` had no pattern for it.
Every "View details" click in the shop returned 404 and the page rendered
"Product not found". One missing line:

```python
path('<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
```

It must stay **last** among the public patterns, or a slug like `featured` or `areas`
would shadow the literal route. Verified: real slug → 200, bogus slug → 404, and all
three literal routes still resolve.

### Two more unhandled HTTP 500s
1. **`Vendor.save()` could write a blank unique slug.** `slugify()` returns `''` for a
   name it strips entirely (e.g. Devanagari). Worse, the *historical* model inside
   `products/0003_seed_areas_and_vendor.py` has no overridden `save()` at all — which is
   exactly why the seeded `Patan Puja Bhandar` shipped with `slug=''`. A blank UNIQUE
   value also means only **one** such vendor can ever exist. Now falls back to
   `vendor-<user_id>`; the migration sets the slug explicitly.
2. **`Area.save()` and `Category.save()` did not uniquify slugs.** Repeating a name (or an
   admin retrying a create) raised `IntegrityError` → **HTTP 500**. Both now suffix the
   slug, the way `Product` already did.

### Responsive polish
- Every admin `<table>` is wrapped in `.table-wrap`: horizontal scroll, a **sticky first
  column** so a scrolled row stays identifiable, a visible scrollbar, and a `min-width`
  so column headers stop crushing.
- The admin sidebar was a fixed 250px column with **no breakpoint at all** — on a 400px
  phone that left 150px of usable content. It is now an off-canvas drawer below 880px,
  with a 44px toggle (comfortable touch target), a scrim, Escape-to-close, and
  auto-close on route change. Extracted as `NavShell`.

### New: `backend/verify_day3c.py` — 128 assertions
Drives the real HTTP API through the whole purchase path, then a
**full pending → confirmed → processing → shipped → delivered ladder**, asserting the
timeline at every single step (exactly one `current`, no later step `done` early, and
all-`done`/terminal at the end).

### New: `manage.py purge_verification_orders`
The verifiers create real rows, which made order ids drift (the admin UI would show "21"
right after "10"). This command removes **only** rows whose `notes` or `shipping_address`
carry a verifier marker, so the 8 seeded demo orders are never touched. Supports
`--dry-run` and `--keep-cart`.

### Verification totals

| Suite | Result |
|---|---|
| `manage.py test` | **113 pass** (was 101) |
| `verify_day2.py` | 68/68 |
| `verify_day3.py` | 55/55 |
| `verify_day3b.py` | 41/41 |
| `verify_day3c.py` | **128/128** |
| **Live assertions** | **292** |

Both frontends build clean. 9/9 API routes, 10/10 customer routes, 7/7 admin routes
return 200. Database after purge: 8 seeded orders · 0 cart lines · 35 products ·
10 categories · 3 areas · 1 vendor · 12 vendor-assigned products · 0 scratch rows.

### Test-harness lesson worth recording
Four of the Day 3.4 "failures" were **my test bugs, not product bugs**: I guessed
`/api/orders/my-orders/` (real: `/api/orders/`), `total` (real: `total_amount`),
top-level `reasons` (real: nested under `recommendation`), and `recommendations` (real:
`recommended_products`). A fifth looked like a bug because `AdminOrderUpdateView` is a
**write-only** endpoint with no GET — reading an order back through it returns 405.
And DRF serializes `DecimalField` as a **string**, so `isinstance(price, float)` is false
on a perfectly correct API. Read the real response before asserting on it.

---


## Day 1 Completed (2026-09-18)

All four Day-1 P0 items are **done and verified**. Verification suite: **34 passed / 0 failed**.

| # | Was | Now |
|---|-----|-----|
| B1 | `frontend` production build failed | **FIXED** — `<Suspense>` added to `auth/login` + `auth/register`; stale `.next*` removed. Build exits 0. |
| B2 | Delivery fee was display-only (order short by Rs. 100) | **FIXED** — `DELIVERY_FEE` is a single setting; persisted on `Order.delivery_fee`; exposed via `GET /api/orders/config/`. Cart quote now equals the order record exactly. |
| B4 | Admin dashboard showed mock data; no login gate | **FIXED** — all mock fallbacks removed, login gate restored and verified against `/api/auth/profile/`, real error/empty/loading states, prediction alerts wired to `/api/analytics/predictions/`. |
| B7 | `router.push()` during render in checkout | **FIXED** — moved into `useEffect`. |
| B8 | Home page masked API failure with hardcoded content | **FIXED** — now renders explicit "unavailable" states; `force-dynamic` set. |

**Verified after the fixes:**
- `frontend` build exit 0 · `admin-dashboard` build exit 0 · `manage.py check` clean
- All 13 pages render 200 (8 customer + 5 admin)
- Live API data confirmed rendering (real festivals + featured products on home)
- Cart quote == order record (the exact bug that was broken)
- Customer → every admin endpoint still **403** (16/16 checks — authorization not weakened)
- Error paths correct: empty-cart checkout 400, over-stock 400, unknown slug 404
- Test orders removed; DB restored to its original 8 orders

**Schema change:** `orders.Order` gained `delivery_fee` (migration `orders/0002`).
Existing seeded orders keep `delivery_fee=0` so their historical totals are untouched.

---

## Stack

Confirmed by inspecting `requirements.txt`, `package.json`, and the running code — not assumed.

| Layer | Technology | Version (verified) |
|---|---|---|
| Frontend (customer) | Next.js App Router + React, JavaScript (not TS) | Next 16.2.2, React 19.2.4 |
| Frontend (admin) | Next.js App Router + React, JavaScript | Next 16.2.2, React 19.2.4 |
| Backend | Django + Django REST Framework | Django 4.2.29, DRF 3.17.1 |
| Auth | JWT via djangorestframework-simplejwt | 5.5.1 |
| DB | **SQLite** (`backend/db.sqlite3`) — PostgreSQL is commented out in settings | — |
| Filtering | django-filter 25.1 | — |
| Images | Pillow 12.2.0, served from `backend/media/` | — |
| Styling | Plain CSS Modules + CSS custom-property design system. No Tailwind, no UI library. | — |
| AI/ML | **None present.** No scikit-learn, no pandas, no model files. | — |

Three separate projects, **three separate git repos** — no repo at the project root.
There is no root-level README, AGENTS.md, or docs/ folder (I created `docs/`).

---

## Working

All items below were **verified live** against a running server (`manage.py runserver` on :8000), not inferred.

**Backend — every public endpoint returns 200:**
`/api/products/`, `/api/products/categories/`, `/api/products/featured/`,
`/api/festivals/kits/`, `/api/festivals/upcoming/`, `/api/festivals/recommendations/`

**Backend — every admin endpoint returns 200 with an admin token:**
`/api/products/admin/products/`, `/api/products/admin/categories/`,
`/api/orders/admin/orders/`, `/api/festivals/admin/kits/`, `/api/festivals/admin/kits/1/items/`,
`/api/analytics/sales/`, `/api/analytics/trending/`, `/api/analytics/inventory/`, `/api/analytics/predictions/`

**Authentication** — works. Verified:
- `admin` / `admin123` → 200 (is_staff, is_superuser, is_admin_user)
- `testuser` / `test1234` → 200 (customer)
- JWT access + refresh issuance works; token refresh is wired in `frontend/src/lib/api.js`.
- Django password hashing is correct (`set_password`, no plaintext).

**Authorization** — works and is correctly enforced. Verified by negative test:
customer token against all three admin surfaces → **403**. Good.

**Cart + checkout** — works end to end. Verified: add to cart → 200, cart totals correct,
checkout → 201 with correct `total_amount`, order items, and stock decrement.

**Seeded data** — present and coherent: 10 categories, 35 products (all with real price/stock/popularity/unit),
7 festival kits, 68 kit items, 5 upcoming festivals, 8 historical orders, 20 order items.
Product images exist in `media/products/` (5 files).

**Design system** — `frontend/src/app/globals.css` is genuinely good: a Nepali-cultural palette
(`--primary: #C41E3A` crimson, `--secondary: #D4A843` gold), tokens for spacing/radius/shadow/transition,
utility classes (`.btn`, `.card`, `.badge`, `.grid-*`, `.form-*`), skeletons and keyframe animations.
This is the foundation to build on — do not replace it.

**Admin dashboard** — **builds successfully** (`next build` → 8 routes, clean).

---

## Broken

Ordered by demo impact. Items struck through were fixed on Day 1.

### ~~B1 — Customer frontend does not build. BLOCKER.~~ FIXED (Day 1)
`useSearchParams()` in `auth/login/page.js` and `auth/register/page.js` had no `<Suspense>`
boundary, and a stale `.next_old_1789714610/` cache was present. Both pages now wrap their
content in `<Suspense>` (copying the pattern from `festivals/page.js`) and the stale caches
were removed. `next build` now exits 0 with all 12 routes generated.

### ~~B2 — Orders silently under-charge by Rs. 100. HIGH.~~ FIXED (Day 1)
The delivery fee was a display-only illusion. Now `DELIVERY_FEE` is defined once in
`core/settings.py`, persisted to `Order.delivery_fee`, included in `Order.total_amount`,
and published to both frontends via `GET /api/orders/config/`. The cart, checkout button,
and saved order all read the same value.
Verified: cart quoted Rs. 950 → order recorded Rs. 950.00.
`OrderItem`-based history and existing seeded orders are unaffected.

### B3 — Recommendation engine is popularity-only. MEDIUM.
`festivals/views.py: RecommendationsView`. It *does* consider upcoming festivals and their kit
items — that part is real. But it collects matching products into a **`set()`**, then slices
`[:12]`. So the returned order is Python set-iteration order, which is arbitrary and unrelated
to any ranking signal: the festival relationship has **no influence on the order** of results.

Verified: three identical calls returned an identical sequence (set order is stable within one
process), so it will not visibly shuffle during a demo — but the sequence is effectively random
with respect to relevance, and not reproducible across runs. There is no score, no explanation,
no per-user signal, and the 12-item cut is arbitrary.

It is a "recommendation" in name only — exactly the fake-button outcome the brief forbids.

Note: the list *content* is defensible (it does pull festival-linked products); it is the
**ranking and explainability** that are absent.

### ~~B4 — Admin dashboard is a prototype, not an admin panel. MEDIUM.~~ FIXED (Day 1)
All four pages no longer fall back to hardcoded mock data — they show real loading, error, and
empty states. `AdminContext` now verifies the token against `/api/auth/profile/` and checks
`is_admin_user` before granting access; unauthenticated visitors are redirected to `/login`
and the sidebar is hidden. Hardcoded credentials removed from the login form. `NEXT_PUBLIC_API_URL`
is honoured. The "Smart Prediction Alerts" panel now calls `/api/analytics/predictions/` for real.
`ProductAdminSerializer` gained `category_name` so the inventory table shows category names
instead of raw IDs.

**Still outstanding (moved to P0 Day 3):** vendor management, customer management, area
management, and the "add/edit" write actions are not built. The dashboard is now *honest*
(read-only) rather than *fake*.

### B5 — Role model is binary; the 4-tier hierarchy does not exist. MEDIUM.
The brief specifies SUPER ADMIN → ADMIN → VENDOR, plus CUSTOMER. What actually exists:
- `accounts.UserProfile.is_admin_user` — a Boolean that until Day 1 was **never read by any
  authorization check**. It is now read by the admin dashboard's client-side gate.
- All *API* admin protection still uses DRF's `IsAdminUser`, which tests **`is_staff`**.
- **There is no VENDOR concept at all.** No vendor field on `Product`, no vendor model, no vendor role.
- There is no distinction between super admin and admin.

So today: `is_staff=True` = full API access; `is_staff=False` + `is_admin_user=False` = customer.
The dashboard gate is a UX guard, **not** a security boundary — the API permission classes remain
the real authority.

### B6 — Areas are a hardcoded 3-value enum, not manageable data. LOW-MEDIUM.
`CITY_CHOICES = kathmandu|lalitpur|bhaktapur` is duplicated in **three separate files**
(`accounts/models.py`, `orders/models.py`, `accounts/serializers.py`). "Manage assigned area"
and "Manage areas" cannot be implemented against a hardcoded enum — an Area model is required.

### B7 — Two competing seed commands. LOW.
`core/management/commands/seed_data.py` and `products/management/commands/seed_data.py` are
byte-identical duplicates. `python manage.py seed_data` resolves to `core`'s (app order in
`INSTALLED_APPS`) — the `products` one is dead code.

### ~~B8 — Frontend fetch pattern is broken by design. MEDIUM.~~ PARTIALLY FIXED (Day 1)
`frontend/src/lib/api.js` still uses `localStorage`, and `app/page.js` is still a Server Component
that fetches during render — but the home page only requests **public** endpoints, so there is
no token dependency, and `dynamic = 'force-dynamic'` now makes the behaviour explicit rather than
accidental. The harder problem — that API failure was masked by a hardcoded fallback festival
list — is **fixed**: the page now renders an explicit "information is unavailable" state.

Remaining: any *authenticated* server-side fetch would still silently degrade. Keep
`useEffect`-based fetching for anything token-dependent.

### B9 — Password reset does not exist. MEDIUM (P1).
No `password_reset` endpoint, no email config, no page. The brief requires it.

### B10 — Security/config debt. MEDIUM.
- `SECRET_KEY` is a literal in `settings.py`; `DEBUG = True`; `ALLOWED_HOSTS = ['*']`;
  `CORS_ALLOW_ALL_ORIGINS = True`.
- `db.sqlite3` and `media/` are committed inside the repo.
- Admin credentials `admin`/`admin123` are seeded by `seed_data` and remain in seed scripts
  (acceptable for demo, must not ship). **The hardcoded form defaults were removed on Day 1.**
- **Functional demo auth gap:** login is username+password even though register collects email —
  no email login, no OTP, no reset. The brief explicitly allows a safe demo mechanism here.
- ~~`frontend/src/app/checkout/page.js` calls `router.push()` during render~~ **FIXED (Day 1)** —
  guards moved into `useEffect`.

---

## Missing

Grouped by whether it blocks the demo.

**Blocks P0:**
- A production build of the customer frontend (B1).
- Delivery fee in the order total (B2).
- A real, ranked, explainable recommendation engine (B3).
- **Product demand prediction — entirely absent.** No model, no endpoint, no page, no data.
- Vendor role and vendor system — absent.
- Admin/customer/area management in the dashboard — absent.
- Order tracking surface for the customer beyond a static status badge.

**P1:**
- Wishlist / favourites.
- Reviews and ratings (no `Review` model exists).
- Password reset.
- Per-vendor and per-area analytics.
- Personalized recommendations from purchase history.

**P2:**
- Payment gateway integration (the mock in `CheckoutView` marks esewa/khalti as `paid`
  unconditionally — acceptable for demo, must be labelled as mocked).
- Notifications, advanced analytics, animations beyond the existing set.

---

## Critical Bugs

Ranked by probability of ruining the demo.

| # | Bug | Severity | Status |
|---|-----|----------|--------|
| 1 | `frontend` `next build` fails (Suspense + stale cache) | **Blocker** | ✅ FIXED Day 1 |
| 2 | Order total omits the displayed Rs. 100 delivery fee | **High** | ✅ FIXED Day 1 |
| 3 | Admin pages show mock data on error, redirect disabled | **High** | ✅ FIXED Day 1 |
| 4 | No demand prediction feature exists at all | **High** | ⬜ Open — Day 2 |
| 5 | Recommendation ranking is not actually ranking (set() ordering) | **Medium** | ⬜ Open — Day 2 |
| 6 | `is_admin_user` unenforced on the API; no VENDOR role | **Medium** | ⬜ Open — Day 3 |
| 7 | `router.push()` during render in checkout | **Medium** | ✅ FIXED Day 1 |
| 8 | Home page masks API failure with hardcoded fallback | **Medium** | ✅ FIXED Day 1 |
| 9 | Hardcoded admin credentials as form defaults | **Medium** | ✅ FIXED Day 1 |

---

## Architecture

Three independently deployed pieces talking HTTP. No monorepo tooling, no Docker, no CI.

```
  Browser
     │
     ├─────────────────────────────┬──────────────────────────────┐
     │                             │                              │
     ▼                             ▼                              │
 frontend/ :3000            admin-dashboard/ :3001                │
 Next.js App Router         Next.js App Router                    │
 Customer storefront        Admin panel (prototype)              │
     │                             │                              │
     │  src/lib/api.js             │  src/lib/api.js              │
     │  Bearer <access_token>      │  Bearer <admin_token>        │
     │  localStorage               │  localStorage                │
     └──────────────┬──────────────┘                              │
                    │                                             │
                    ▼                                             │
        two independent JWT clients, no shared code ──────────────┘
                    │
                    ▼
        backend/  Django 4.2 + DRF  127.0.0.1:8000
        ┌───────────────────────────────────────────────┐
        │ Routing  core/urls.py                         │
        │   /api/auth/      → accounts   (register/login│
        │                                 /refresh/prof)│
        │   /api/products/  → products   (catalog+admin)│
        │   /api/orders/    → orders     (cart/checkout)│
        │   /api/festivals/ → festivals  (kits/recs)    │
        │   /api/analytics/ → analytics  (admin only)   │
        │   /admin/         → Django admin              │
        │                                               │
        │ AuthN: SimpleJWT (Bearer), 1d access / 7d ref │
        │ AuthZ: AllowAny | IsAuthenticated | IsAdminUser│
        │        IsAdminUser == is_staff (NOT is_admin_user)│
        │                                               │
        │ Apps:                                         │
        │  accounts  ─ UserProfile(1:1 User, city, flag)│
        │  products  ─ Category → Product               │
        │  festivals ─ FestivalKit → KitItem → Product  │
        │              UpcomingFestival(date)           │
        │  orders    ─ Cart(user,product)               │
        │              Order → OrderItem(product_name   │
        │                       snapshot, price)        │
        │  analytics ─ stateless aggregations, no models│
        └───────────────────────────────────────────────┘
                    │
                    ▼
        SQLite  backend/db.sqlite3   +   media/ (images)
        No Area model. No Vendor model. No Review model.
```

**Data model that exists:** `User → UserProfile`; `Category → Product`;
`FestivalKit → KitItem → Product`; `UpcomingFestival`; `Cart`; `Order → OrderItem`.
`OrderItem` correctly snapshots `product_name` and `price` (good — orders survive price changes).

**Notable:** `analytics` has no models — it is pure read-only aggregation over `orders`/`products`.
That is the right call and should be preserved.

---

## Day 1 Test Record

Required format: Feature · Test performed · Result · Known limitation.

| Feature | Test performed | Result | Known limitation |
|---|---|---|---|
| Frontend build | `next build` from clean cache | ✅ exit 0, 12 routes | — |
| Admin build | `next build` from clean cache | ✅ exit 0, 8 routes | — |
| Backend integrity | `manage.py check` + `migrate` | ✅ no issues, migration applied | — |
| Public endpoints (11) | GET each, assert 200 | ✅ 11/11 | — |
| Auth | correct + wrong password + no token | ✅ 200 / 401 / 401 | No email or OTP login |
| Authorization (16) | customer vs admin on 8 admin endpoints | ✅ 8×403, 8×200 | Only `is_staff` tiers exist |
| Delivery fee math | cart `subtotal + fee == total` | ✅ exact | — |
| Delivery fee persistence | cart quote vs stored `total_amount` | ✅ 190.00 == 190.00 | — |
| Checkout → cart clear | order created, cart count 0 | ✅ | — |
| Order list / detail | GET both as owner | ✅ 200 | No customer-side status timeline |
| Empty-cart checkout | POST with empty cart | ✅ 400 | — |
| Over-stock add | POST quantity 99999 | ✅ 400 | — |
| Unknown product | GET bad slug | ✅ 404 | — |
| Page rendering (13) | GET every route | ✅ 13/13 = 200 | — |
| Live data on home | grep rendered HTML | ✅ real festivals + products | — |
| Admin login gate | verify `/api/auth/profile/` → `is_admin_user` | ✅ enforced client-side | API still keyed on `is_staff` |
| Admin prediction alerts | wired to `/api/analytics/predictions/` | ✅ real alerts render | Still rule-based, not a model |
| Admin product category | `category_name` in serializer | ✅ name not ID | — |

**Regression checked:** after every change, the six public endpoints and the customer 403
boundary were re-verified. Authorization was **not** weakened at any point.

---

## Priority

### P0 — must work for the demo
| # | Item | Status |
|---|------|--------|
| 1 | Fix frontend build (Suspense + clear stale `.next*`) | ✅ **Done** |
| 2 | Delivery fee actually included in `Order.total_amount` | ✅ **Done** |
| 3 | Customer browsing → detail → cart → checkout → order history | ✅ Works (re-verified) |
| 4 | Festival / kit / samagri browsing | ✅ Works |
| 5 | Admin dashboard wired to real APIs, login gate restored | ✅ **Done** |
| 6 | Ranked, explainable recommendation engine | ✅ **Done** |
| 7 | Product demand prediction (model + endpoint + admin UI) | ✅ **Done** |
| 8 | Vendor role + vendor product management | ✅ **Done** |
| 9 | Super Admin / Admin / Vendor split with real enforcement | ✅ **Done** |
| 10 | `Area` model + area management | ✅ **Done** |
| 11 | Admin CRUD write actions (products, categories, areas) | ✅ **Done** |
| 12 | Customer order tracking / status timeline | ✅ **Done** — 5-step timeline + distinct cancelled state |
| 13 | Responsive polish + four-state audit on every screen | ✅ **Done** — tables scroll & pin, sidebar is a drawer under 880px |
| 14 | Full demo rehearsal | ✅ **Done** — automated as `verify_day3c.py` (128 assertions) |
| 15 | Routed product detail endpoint (`/api/products/<slug>/`) | ✅ **Done** — was missing entirely |

### P1
Wishlist · reviews/ratings · password reset (B9) · vendor analytics · admin analytics polish ·
personalized recommendations from order history · real prediction dashboard.

### P2
Live payment gateways · notifications · advanced analytics · extra animation work.

**Rule: no P2 work while any P0 is open.**

---

## Recommended implementation order (2–3 days)

Deliberately ordered so the **demo is never in a worse state than the previous step**,
and the shopping flow is verifiable at all times.

**Day 1 — make it build, make it trustworthy**
1. Fix `frontend` build: wrap `useSearchParams` pages in `<Suspense>`, delete
   `.next_old_1789714610/`, rebuild, confirm a clean production build. *(unblocks everything)*
2. Fix the delivery fee: add a single `DELIVERY_FEE` constant, include it in
   `CheckoutView`'s total, and remove the two `- 100` / `+ 100` hacks in the order-detail
   and cart pages. *(one source of truth)*
3. Replace the checkout `router.push()`-during-render with `useEffect`.
4. Fix `AdminContext`: restore the login redirect, remove mock-data fallbacks, surface errors.
5. Run the full E2E pass: browse → product → cart → checkout → history, on desktop and mobile widths.

**Day 2 — the differentiators (this is what the project is judged on)**
6. Rebuild recommendations as a real scored, explainable engine
   (festival/puja → required samagri → matching products + popularity + category relevance,
   with a visible `reasons[]` per product). Write `docs/AI-RECOMMENDATION.md`.
7. Build demand prediction: synthetic-but-labelled seasonal dataset → a genuine trained model
   with a real evaluation metric → `/api/analytics/demand-forecast/` → admin UI. Write `docs/AI-PREDICTION.md`.
8. Surface both in the UI (recommendations page + admin forecast panel).

**Day 3 — roles, management, polish**
9. Introduce the `Area` model and the VENDOR role; make `is_admin_user`/role actually load-bearing
   in authorization; split super admin from admin.
10. Wire admin CRUD for products / kits / orders / areas / vendors (replace the dead buttons).
11. Order tracking, empty/loading/error states, responsive pass.
12. Rehearsal: run the demo script twice end to end, fix whatever breaks.

---

## Decisions requiring your approval

These are the only choices I cannot safely infer from the repo. Everything else I will decide myself.

1. **Vendor scope.** The spec asks for a full VENDOR role, but there is no vendor concept in the
   DB and no vendor UI anywhere. Building real multi-vendor order splitting is a large feature.
   My recommendation: model `Vendor` and attach `vendor` to `Product`, add vendor-scoped product
   and order visibility, and keep **one** vendor account for the demo. Full order-splitting stays P1.
   → Confirm this scope, or tell me to attempt full multi-vendor.

2. **Demand prediction data.** There are only 8 orders across 9 distinct days with 6 distinct
   products — nowhere near enough to train a credible model. My recommendation: generate a
   clearly-labelled **synthetic seasonal sales dataset** (documented as synthetic in
   `docs/AI-PREDICTION.md`, never presented as real demand) and train a genuinely working
   model on it that reports an honest accuracy metric.
   → Confirm synthetic data is acceptable, or point me at a real dataset.

3. **Database.** SQLite is in use and works. I intend to **keep SQLite** for the deadline
   (Postgres is already stubbed out in settings if you want it later).
   → Confirm, or tell me to switch to PostgreSQL now.

4. **Feature-phone / wording default.** No blocking question here — I will reuse the existing
   seeded festival data (Dashain, Tihar, Shivaratri, Bratabandha, Pasni, Griha Pravesh, Shraddha)
   and will not invent religious claims.

I have **not** modified any existing application code. Only `docs/` and the new root
`AGENTS.md` were added.
