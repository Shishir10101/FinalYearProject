# DEVELOPMENT-ROADMAP.md

Target: **demo-ready in 2–3 days.**
Read `docs/CURRENT-STATE.md` for the evidence behind each item.

Guiding principle: **the demo must never be worse than the previous step.** Every phase
leaves a working application behind it. The shopping flow already works — protect it.

---

## Where we are

| Area | State |
|---|---|
| Backend API (public + admin) | ✅ all 200 |
| Auth + authorization | ✅ works, 403 correctly enforced |
| Cart → checkout → order history | ✅ works end to end |
| Festival kits / samagri | ✅ works |
| Seeded data | ✅ 35 products, 7 kits, 10 categories |
| Customer frontend **build** | ✅ **fixed Day 1** |
| Delivery fee in order total | ✅ **fixed Day 1** |
| Admin dashboard | ✅ **de-gated + de-mocked Day 1** (read-only) |
| Recommendations | ✅ **ranked + explainable Day 2** (23 tests) |
| Demand prediction | ✅ **built Day 2** — real model, labelled synthetic data (33 tests) |
| Festival calendar | ✅ **repaired Day 2** — all rows were in the past |
| Vendor role | ❌ does not exist → **Day 3** |
| Areas | ⚠️ hardcoded 3-value enum → **Day 3** |

---

## Day 1 — Make it build. Make it trustworthy. ✅ COMPLETE

**All five items done and verified. Verification suite: 34 passed / 0 failed.**

### 1.1 Fix the customer frontend build `P0` ✅
Wrapped `auth/login/page.js` and `auth/register/page.js` in `<Suspense>`; removed the stale
`.next_old_1789714610/` directory, `build.log`, `build.txt`.
**Result:** `next build` exits 0, 12 routes generated.

### 1.2 Delivery fee — one source of truth `P0` ✅
`DELIVERY_FEE = 100` defined in `core/settings.py`. Persisted to a new `Order.delivery_fee`
column (migration `orders/0002`), included in `Order.total_amount`, and published via
`GET /api/orders/config/`. All three UI pages now read the API value instead of doing
`+100` / `-100` arithmetic.
**Result:** cart quoted Rs. 950 → order recorded Rs. 950.00. Seeded orders untouched.

### 1.3 Fix `router.push()` during render `P0` ✅
Both guards moved into `useEffect`; added a proper loading return.

### 1.4 Admin dashboard — stop faking it `P0` ✅
Removed every mock-data fallback. Rewrote `lib/api.js` with real error handling.
`AdminContext` now verifies the token against `/api/auth/profile/` and checks `is_admin_user`;
added an `AuthGate` that blocks content and redirects to `/login`. Sidebar hidden when
unauthenticated. Hardcoded credentials removed. `NEXT_PUBLIC_API_URL` honoured.
Prediction alerts wired to `/api/analytics/predictions/`. Added `category_name` to the product
admin serializer. Added loading/empty/error states + a responsive pass.

### 1.5 Full E2E verification `P0` ✅
34 assertions across 5 groups — all passed. 13/13 pages render 200. Test orders removed and
the DB restored to its seeded 8 orders.

---

## Day 2 — The differentiators. ✅ COMPLETE

This is what the project is actually judged on. Everything else is table stakes.

> **Day 2 outcome:** both AI features are built, tested and surfaced in the UI.
> 56 backend unit tests + 68 live E2E assertions pass; authorization re-verified
> (18 checks). The recommendation engine returns a **ranked, fully explainable**
> list. The forecast model is **genuinely trained** and **beats a naive baseline
> by 13.5 %** on a held-out window, fitted on data that is **openly labelled
> synthetic** in the code, the API and the UI.

### 2.1 Real recommendation engine `P0` ✅
Rebuilt `festivals/views.py::RecommendationsView` as a scored, explainable ranker.

```
Festival / Puja
      ↓
Required samagri            (KitItem.is_required → +60 / +30)
      ↓
Staple samagri              (nithya categories, when a festival is ≤21d → +28)
      ↓
Candidate products
      ↓
Score =  festival_required   +60
       + festival_optional   +30
       + staple_samagri      +28
       + user_category       +22
       + user_kit_affinity   +16
       + user_repeat         +14
       + popularity          +8..+12
      ↓
Ranked list + reasons[] per product
```

- ✅ Returns a **list**, not a `set()` — ordering is now deterministic (asserted across 5 rebuilds).
- ✅ Each recommendation carries a human-readable `reason` with `code` + `points` + `text`.
- ✅ Cold-start path works (anonymous visitors get festival + popularity signals).
- ✅ Logic isolated in `Recommender` — **23 unit tests**.
- ✅ Documented in `docs/AI-RECOMMENDATION.md` with real weights and a live worked example.
- ✅ **Also fixed a latent blocker:** all 5 `UpcomingFestival` rows were in the *past*, which
  had silently reduced the whole endpoint to "popular products". Repaired via a new
  idempotent `refresh_festivals` management command.
- **Done when:** the recommendations page shows ranked products with visible reasons, and the
  order changes when the upcoming festival changes. ✅ verified live (8/8 reasons rendered).

### 2.2 Demand prediction `P0` ✅
Built as a separate feature, not folded into recommendations.
- ✅ Real history confirmed insufficient (8 orders / 20 items / 5 products / 9 days) →
  generated a clearly-labelled **synthetic** seasonal dataset: **14,000 rows, 35 products,
  400 days**, fixed seed for reproducibility, in its own table with a per-row `is_synthetic` flag.
- ✅ A genuinely simple, dependency-free model: multiplicative decomposition
  `level × weekday × festival-ramp × damped-trend`. **No scikit-learn/numpy added**
  (would be ~60 MB for an 8-order dataset).
- ✅ Honest evaluation: **28-day holdout** — mean MAPE **26.20 %**, MAE **0.810** vs
  naive **0.936** (**+13.5 % better than baseline**). Reported as mediocre rather than inflated.
- ✅ Served at `GET /api/analytics/demand-forecast/` with `horizon`/`limit`/`product` params.
- ✅ Labelled synthetic in the code, the API response (`data_source`, `is_synthetic`,
  `provenance_note`) and the UI (warning banner) — asserted by tests.
- ✅ `docs/AI-PREDICTION.md` documents approach, features, metric, and 7 named limitations.
- **Bonus evidence it is a real model:** it independently recovered the Saturday demand spike
  (1.30 truth → **1.191** learned) and Tuesday trough (0.90 → **0.842**) without being told.
- **Done when:** the admin can see a per-product forecast with a stated accuracy figure, and the
  docs are honest about the data's origin. ✅

### 2.3 Surface both in the UI `P0` ✅
- ✅ Recommendations: reasons rendered per product in amber callouts, urgency badge
  (`In 6 days`), festivals as clickable chips, honest "sign in to personalise" note.
- ✅ Admin: new **Demand Forecast** page (nav item) with summary cards, restock-priority table,
  inline SVG sparklines, MAPE badges, and a per-row **"Why?"** expander exposing the model's
  fitted level / trend / weekday factors.
- ✅ Real prediction alerts: added `forecast_restock` alerts driven by predicted demand vs stock,
  replacing the previous mock block.


---

## Day 3 — Roles, management, polish. ✅ COMPLETE

### 3.1 Roles that actually do something `P0` ✅
- ~~Add an `Area` model; migrate the three hardcoded `CITY_CHOICES` copies to one source.~~ ✅
  `core/constants.py` + `products.Area`, seeded at byte-identical slugs so existing
  order data still resolves.
- ~~Introduce `Vendor` and a `vendor` FK on `Product`.~~ ✅ 1:1 with `User`; nullable FK,
  12 of 35 products assigned.
- ~~Make the role the thing permissions read — `is_admin_user` is currently decorative.~~ ✅
  `UserProfile.role` is authoritative; `is_admin_user` is derived and kept in sync by `save()`.
- ~~Split **Super Admin** from **Admin**.~~ ✅ Four roles: `super_admin` / `admin` /
  `vendor` / `customer`.
- ~~Add `IsSuperAdmin` / `IsVendorOrAdmin` helpers. No inline `is_staff` checks.~~ ✅
  `core/permissions.py` exposes 4 permission classes and 6 helpers.
- **Never weaken an existing check to make a screen work.** ✅ Honoured — customer
  still 403 everywhere, and vendor is now confined to 12 of 35 products.

### 3.2 Admin CRUD `P0` ✅
- ~~Products~~ ✅ create / edit / delete / enable-disable, with real per-field validation
- ~~Categories~~ ✅ full CRUD on the new Catalog Settings page
- ~~Areas~~ ✅ full CRUD, including per-area delivery-fee overrides
- Vendors: read + write endpoints exist and are scoped; a dedicated vendor-management
  screen was **not** built (the API is ready, the UI is a P1 follow-up).
- Kit items: write endpoints exist (`/festivals/admin/kits/<id>/items/`); the kit editor
  UI was not rebuilt. **Not a regression** — the Day 1 dead buttons were removed rather
  than left lying, and the endpoints work.

### 3.3 Order tracking + states `P0/P1` ✅
- ~~Customer-visible status progression~~ ✅ A 5-step timeline (`pending → confirmed →
  processing → shipped → delivered`), with `cancelled` as a distinct 2-step terminal
  state. Exposed by `OrderSerializer.get_timeline()`, rendered with a responsive
  horizontal/vertical tracker.
- ~~Audit all async surfaces for loading / success / empty / error~~ ✅ Order detail and
  account pages rebuilt. Both previously swallowed errors with `console.error`, so a
  backend outage rendered as *"No orders yet"* — the customer was told the wrong thing.
- Consistent product cards — **not done**; the existing cards vary slightly between home
  and recommendations. P1.

### 3.4 Final polish + rehearsal `P0` ✅ COMPLETE
- ~~Responsive pass on the new timeline~~ ✅ (vertical layout under 640px)
- ~~Reduced-motion support~~ ✅ for the new pulse/shimmer animations
- ~~Responsive sweep of the older admin tables~~ ✅ every admin `<table>` is now wrapped in
  `.table-wrap` (horizontal scroll + a sticky first column) and the fixed 250px sidebar
  collapses into an off-canvas drawer below 880px, with a 44px touch target and Escape-to-close.
- ~~Demo rehearsal~~ ✅ driven as an automated E2E script instead of a manual run-through
  (`backend/verify_day3c.py`, 128 assertions covering the whole purchase path).

### Day 3 bugs found and fixed
1. `get_role()` checked `is_staff` before `profile.role` → vendors resolved to **admin**.
2. The role backfill used `update()` against a non-existent profile → silently 0 rows,
   leaving `vendor1` without a profile and **still** admin.
3. `AdminVendorDetailView` used `IsSuperAdmin` while its list view used `IsStaffRole` →
   an ADMIN saw vendors in the list then got 403 opening any one of them.
4. `UserProfileSerializer` did not expose `role` → the dashboard could not adapt its UI.
5. `CheckoutSerializer.shipping_city` hardcoded the three slug choices → an area added
   through Settings was **rejected at checkout**, making the new `Area` model decorative.
6. The customer city dropdown and the account-page city dropdown were hardcoded
   `<option>` lists → same problem on the read side.
7. A delivered order's timeline still marked the last step `current`, so a finished
   order looked permanently in-progress.

### Day 3.4 bugs found and fixed (responsive + E2E pass)
8. **`ProductDetailView` was never routed.** The view existed, `ProductListSerializer`
   published a `slug`, and the customer detail page called `/api/products/<slug>/` — but
   `products/urls.py` had no pattern for it, so **every "View details" click failed with
   "Product not found"**. Added `path('<slug:slug>/', ...)` last among the public routes
   so it cannot shadow `featured/`, `categories/`, or `areas/`. This was the single most
   user-visible defect in the project.
9. **`Vendor.save()` could produce a blank unique slug.** `slugify()` returns `''` for a
   name it strips entirely (e.g. Devanagari), and the seed migration's historical model
   has no overridden `save()` at all — so the seeded `Patan Puja Bhandar` shipped with
   `slug=''`. A blank UNIQUE value also means only **one** such vendor can ever exist.
   Now falls back to `vendor-<user_id>`, and the migration sets the slug explicitly.
10. **`Area.save()` / `Category.save()` did not uniquify slugs.** Repeating a name (or an
    admin retrying a create) raised an **unhandled `IntegrityError` → HTTP 500**. Both now
    suffix the slug like `Product` already did.
11. **The verifiers left test data behind.** Each run created real orders and areas and only
    cancelled the orders, so ids drifted (the admin UI showed "21" after "10"). Added
    `manage.py purge_verification_orders` (with `--dry-run`), which removes only rows whose
    `notes`/`shipping_address` carry a verifier marker and never touches the seeded set.

**Correction to item 7's framing:** the delivered-timeline fix was real, but the *test* that
"found" it was reading the order through the admin write-only endpoint, which returns no
timeline. It was replaced with a full pending→delivered ladder that asserts all five states.

---

## Day 4 — trust & honesty pass ✅ (2026-09-19)

**Theme:** no new headline features. This day exists to make the existing ones *true* —
to close the gaps the documentation itself admitted to, and to fix what turned up
while doing it.

### 12. The order timeline could not say *when*

The tracker was derived from the single mutable `Order.status` column. It could
answer "where is my order" but never "when did it get there" — the transitions were
simply not stored, so every completed step was permanently undated. Added
`OrderStatusEvent`, an append-only log written from exactly two places (checkout, and
`AdminOrderUpdateView.perform_update()`), and only for a genuine transition.
`timeline.steps[].at` now carries a real timestamp.

`created_at` uses `default=timezone.now`, **not** `auto_now_add`. The latter silently
discards any value passed to it, so the backfill migration could not have preserved
the eight existing orders' real `created_at`. There is a regression test for exactly
this, because it is the same family of trap as the seed migrations that shipped a
blank vendor slug.

A step with no recorded event returns `at: null` and the UI says "not recorded".
Borrowing `created_at` would be inventing a delivery date. `pending` is the one
honest exception — an order *was* necessarily placed at `Order.created_at`.

### 13. Password reset did not exist (B9, required by the brief)

Built on Django's `PasswordResetTokenGenerator`, which buys two properties for free:
the token hash includes the password hash and `last_login`, so a link stops working
once used, and also stops working if the owner logs in first. No token column, no
cleanup job.

Always the same 200 and the same wording whether or not the address has an account. A
bad uid is byte-identical to a bad token. Both endpoints are throttled. A mail failure
is logged rather than surfaced, because a 500 only happens when an account matched —
which would leak the very fact the generic message protects.

Two caveats recorded rather than hidden: `PASSWORD_RESET_EXPOSE_LINK` returns the link
in the response so the flow can be demoed without a mailbox (it is enumeration by
design, so it is asserted to leak exactly two fields and the production shape is
asserted separately), and **a reset does not revoke existing JWTs**.

### 14. `Catalog Settings` was completely broken

Four calls to a bare `setFieldError({})`. The setter lives inside the `useCrud` hook
and is only reachable as `c.setFieldError`, so every "+ New Category", "Edit",
"+ New Area" and "Edit" button threw `ReferenceError` before its dialog could open.

The ESLint config does not enable `no-undef`, so `next lint` was clean. Turning it on
found all four immediately — and confirmed they were the only ones in either app:

```
npx eslint --rule '{"no-undef":"error"}' src/
```

### 15. Per-field validation was dead code

The products modal always set `_general`, so the per-field `<span>`s next to each
input were unreachable. It also had its own weaker copy of `fieldErrors()` that
dropped `non_field_errors`/`detail` into keys nothing rendered — a cross-field
rejection would have failed **silently**. Both modals now use the shared helper,
which joins every message per field and guarantees a fallback, plus a safety net for
any field with no input on screen.

### 16. Three data-integrity holes

Found by probing the live API for the error *shapes* the dashboard would have to
render. All three were accepted:

| Payload | Consequence |
|---|---|
| `price: -5` | Subtracts from the cart total |
| `delivery_fee: -50` on an `Area` | The store pays the customer to deliver |
| Duplicate category name | Filed as `puja-oils-ghee-1` — one category becomes two, both shown in the storefront |

Fixed with `MinValueValidator(0)` (migration `products/0004`) plus a case-insensitive
name check. The slug suffixer **stays** as the last-resort net for the paths the name
check cannot cover; the check is what stops duplicates actually happening.

### 17. There was no rollback path at all

`backend/` and the project root were not git repositories, and the entire Day 1–3 body
of work was uncommitted in both frontends. Created the root repo (covering `backend`,
`docs`, `AGENTS.md`, `README.md` — the two frontends stay independent), committed all
three, and added `.gitignore` files.

### Verification

| Suite | Result |
|---|---|
| `manage.py test` | **178 pass** (was 136) |
| `verify_day4.py` | **88/88** |
| `verify_day2/3/3b/3c` | 68 · 55 · 41 · 128 — **no regression** |
| **Live assertions** | **380** |

Both frontends build clean (13/13 and 10/10 routes). Authorization not weakened.
Database restored to seeded state after purging.

### New commands

`manage.py purge_verification_users` (with `--dry-run`) — the reset flow needs a
throwaway account, and a stray login must not survive the run.

---

## P1 — after P0 is complete

- Wishlist / favourites
- Reviews and ratings (needs a new `Review` model)
- Vendor self-service screen (API is complete and scoped; no UI exists)
- Kit editor UI
- Vendor analytics, area analytics
- Puja-centric home landing (the home page still leads with a generic product grid)
- Consistent product cards across home / products / recommendations
- Search relevance tuning (currently `icontains`, no typo tolerance)
- Image upload widget
- **JWT revocation on password reset** — needs a blacklist or per-user token version

## P2 — only if P0 and P1 are done

- Live eSewa/Khalti integration (the current mock marks them paid unconditionally — fine for
  a demo, must be labelled as mocked)
- Notifications, advanced analytics, extra animation work

**No P2 work while any P0 is open.**

---

## Risk register

| Risk | Likelihood | Mitigation |
|---|---|---|
| Frontend build stays broken | Low — cause identified | Fix first, verify with a clean build |
| Fixing the fee breaks seeded orders | Medium | Historic orders keep their stored totals; only change new checkout + display |
| Synthetic data criticised as fake | Medium | Label it everywhere, report a real metric, document the limitation openly |
| Vendor/multi-vendor scope explodes | **High** | Keep it to one vendor + a real role; full order-splitting stays P1 |
| Role change breaks existing admin login | Medium | Verify `admin` still passes every admin endpoint after each permission change |
| Running out of time on Day 3 | Medium | Day 1 + Day 2 alone are already a defensible demo |

---

## Definition of done — for the whole project

- [ ] Both frontends build with zero errors
- [ ] Customer E2E flow works: browse → festival/category → product → cart → checkout → history
- [ ] All four roles log in; each is refused on surfaces it does not own
- [ ] Recommendations are ranked and carry visible reasons
- [ ] Demand prediction returns a real forecast with a stated accuracy metric
- [ ] Admin dashboard shows live data only, gated by login
- [ ] Product ↔ festival ↔ puja ↔ samagri ↔ kit relationships are browsable
- [ ] Responsive on desktop, tablet, mobile
- [ ] No fake buttons, no dead links, no mock data in the UI
- [ ] No secrets or hardcoded credentials in source
- [ ] Demo rehearsed twice, end to end
