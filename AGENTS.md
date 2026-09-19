# AGENTS.md

Permanent instruction file for coding sessions on this repository.
Written from the actual codebase — every path, model, and command below was verified.

**Read `docs/CURRENT-STATE.md` first.** It holds the live status of what works, what is
broken, and what is missing. This file holds the rules for changing it.

---

## 1. Project purpose

An Online **Puja Samagri** e-commerce platform for **Kathmandu Valley**
(Kathmandu, Lalitpur, Bhaktapur), Nepal.

The differentiator is the **Puja/Festival domain**, not generic retail. Discovery must work
through **six** entry points, not just a product grid:

```
Product · Category · Festival · Puja · Samagri · Ready-made Kit
```

Products must be reachable via their festival/ritual relationships and the required-samagri
they satisfy. A generic shop with a "religious" category bolted on is a failed project.

**All six entry points now exist.** Puja was the last to be built (Day 6): it had no model,
endpoint or page, and `festival_type` was doing double duty for calendar festivals *and* rites
of passage. See `Puja` / `PujaItem` in §3 and `docs/FEATURES.md` §1.

Two AI components are **required**, separate from each other:
1. **Recommendation** — what this user should buy.
2. **Demand prediction** — how much of a product will be needed.

---

## 2. Technology stack (do not change)

| Layer | Technology | Version |
|---|---|---|
| Backend | Django + DRF | 4.2.29 · DRF 3.17.1 |
| Auth | SimpleJWT | 5.5.1 |
| Admin (customer-facing) | Django admin at `/admin/` | — |
| Database | **SQLite** (`backend/db.sqlite3`) | — |
| Frontend (customer) | Next.js App Router, **JavaScript** | 16.2.2 · React 19.2.4 |
| Frontend (admin) | Next.js App Router, **JavaScript** | 16.2.2 · React 19.2.4 |
| Styling | **CSS Modules + `globals.css` tokens** | — |

**Hard rules:**
- **Do not** introduce Tailwind, shadcn, MUI, Chakra, styled-components, or any UI kit.
- **Do not** convert the frontends to TypeScript.
- **Do not** switch the DB away from SQLite without explicit approval.
- **Do not** add microservices, Celery, Redis, Docker, or a message queue.
- **Do not** add a state library (Redux/Zustand). React Context is already set up and sufficient.
- **Do not** add an ML framework heavier than scikit-learn + pandas/numpy.
- **Prefer the standard library and what is already installed.** Adding a dependency needs a reason.

> **Next.js 16 warning.** `admin-dashboard/AGENTS.md` and `frontend/AGENTS.md` say this Next.js
> has breaking changes versus older training data. Check `node_modules/next/dist/docs/` before
> using an unfamiliar API. Two concrete traps, both of which cost real time:
>
> 1. `useSearchParams()` **must** be inside a `<Suspense>` boundary or the production build fails.
> 2. **`params` and `searchParams` are Promises in a Server Component.** `const { slug } = params`
>    yields `undefined` — every valid dynamic route would 404, and **the build does not catch
>    it**, because the mistake is a runtime value, not a syntax error. Always `await`:
>    ```js
>    export default async function Page({ params }) {
>      const { slug } = await params;
>    }
>    ```
>    Confirmed in `node_modules/next/dist/docs/01-app/01-getting-started/03-layouts-and-pages.md`.
>
> Also worth knowing: `notFound()` renders the 404 UI but returns a **200** status when the
> response has already started streaming (a `loading.js` or any `await` opens that boundary).
> Next injects `<meta name="robots" content="noindex">` as the mitigation. See
> `dist/docs/01-app/02-guides/streaming.md`.

---

## 3. Architecture

Three independently deployed projects. **Three separate git repositories** — the project root
is *not* a repo.

```
project_7/
├── backend/            Django + DRF, SQLite, :8000
├── frontend/           Next.js customer storefront, :3000
├── admin-dashboard/    Next.js admin panel, :3001
├── docs/               Development references
└── AGENTS.md           This file
```

Request flow — two independent JWT clients, **no shared code between them**:

```
frontend/src/lib/api.js      → Bearer access_token (localStorage)  ─┐
admin-dashboard/src/lib/api.js → Bearer admin_token (localStorage) ─┤
                                                                   │
                                            backend/ core/urls.py ◄─┘
```

### Backend app map

| App | Models | Responsibility | Admin URLs |
|---|---|---|---|
| `core` | — | settings, routing, `constants.py` (**`CITY_CHOICES`**), `permissions.py` (**the role system**) | — |
| `accounts` | `UserProfile` (1:1 `User`) | register, login, JWT refresh, profile, **`role`** | — |
| `products` | `Area`, `Vendor`, `Category` → `Product` | catalog, search/filter/sort, **vendor ownership**, **delivery areas** | `/api/products/admin/...` |
| `festivals` | `FestivalKit` → `KitItem` → `Product`, `UpcomingFestival`, **`Puja` → `PujaItem`** | kits, festivals, **rituals**, recommendations (`recommender.py`) | `/api/festivals/admin/...` |
| `orders` | `Cart`, `Order` → `OrderItem` | cart, checkout, order history | `/api/orders/admin/...` |
| `analytics` | `SyntheticSalesRecord` | aggregation + demand forecasting (`forecasting.py`) | `/api/analytics/...` |

`analytics` owned **no models** until Day 2. It now owns exactly one:
`SyntheticSalesRecord`, which holds the **synthetic** sales history the forecaster
trains on. That is a deliberate, narrow exception — it exists only so fabricated
rows can never be mixed into the real `orders` tables. **Do not add further models
to `analytics`**; aggregation over `orders` remains the right design.

`core` gained two responsibilities on Day 3 that must not be duplicated elsewhere:
`constants.py` (shared enum values) and `permissions.py` (the single source of
truth for who may do what). See §8.

### Key model facts
- `Product` has `slug` (auto-generated, uniqueness-enforced), `stock`, `popularity_score`,
  `is_featured`, `is_active`, `unit`, and **`vendor`** (`FK → Vendor`, `SET_NULL`, nullable).
  **23 of 35 products have no vendor** — never make this field required.
- `Vendor` is 1:1 with `User`. That link is what makes vendor scoping enforceable.
- `Area` replaced the hardcoded `CITY_CHOICES` enum. Its seeded `slug` values are
  byte-identical to the old enum values (`kathmandu`/`lalitpur`/`bhaktapur`) so
  existing `Order.shipping_city` and `UserProfile.city` data still resolves.
  **Never change those three slugs** without a data migration.
- `KitItem` has `is_required` — this is the **Required Samagri** mechanism. Use it.
- `OrderItem` **snapshots** `product_name` and `price`. Never replace this with a live FK read.
- **`Puja` is the ritual; `FestivalKit` is one purchasable bundle that serves it.** They are
  deliberately separate. `FESTIVAL_CHOICES` conflates calendar festivals (`dashain`, `tihar`,
  `shivaratri`) with rites of passage (`bratabandha`, `pasni`, `griha_pravesh`, `shraddha`), and
  two of its labels even end in "Puja". A ritual can exist with **no** kit — 3 of the 8 seeded
  ones do — so never assume `Puja.kit` is set. `FestivalKit.puja` is a nullable `SET_NULL` FK.
- **`PujaItem` and `KitItem` are not redundant.** A kit's optional extras are a merchandising
  decision; a puja's list is the ritual requirement. The seeded rituals take their lists from
  the project's own kit data, so the two agree today — that is a seeding choice, not a
  constraint.
- **`Puja.kit` is a property that walks `self.kits.all()`, not `.filter()`.** `.filter()` on a
  related manager bypasses the prefetch cache and issues one query per row, turning a list
  endpoint into N+1. `test_list_query_count_does_not_grow_with_the_number_of_rituals` guards it.
- **`seed_pujas` must stay a command, never a data migration.** Products, categories and kits are
  created by `seed_data`, not by any migration, so a migration seeding puja items would find an
  empty catalogue on a fresh database and quietly produce rituals with no samagri.
- `OrderStatusEvent` (Day 4) is an **append-only** log of status transitions. It is written from
  exactly two places — `CheckoutView` and `AdminOrderUpdateView.perform_update()` — and only for a
  genuine change. Never write one for an unchanged status: the customer's timeline fills with
  duplicate steps. `created_at` uses `default=timezone.now`, **not** `auto_now_add`, so the
  backfill migration could preserve real historical timestamps. `timeline.steps[].at` is `null`
  when nothing was recorded, and the UI must say "not recorded" rather than invent a time.
- `FestivalKit.total_price` / `original_price` are `@property` methods that recompute from
  items on every access. Do not duplicate this math in a serializer.
- `SyntheticSalesRecord.is_synthetic` is always `True`. It is stored per row so the
  provenance invariant is queryable rather than implied by the table name.
- `UpcomingFestival.date` must be in the **future** for the recommender to work. If
  recommendations look like a plain best-seller list, run `refresh_festivals` first.
- `UserProfile.role` is authoritative. **`is_admin_user` is legacy and derived** —
  `save()` force-syncs it from `role`. Never read it for an authorization decision.
- **Every `SlugField(unique=True)` must uniquify inside `save()`.** `Product`, `Vendor`,
  `Area`, and `Category` all suffix now (`base`, `base-1`, `base-2`…). A plain
  `slugify()` raises `IntegrityError`, which the API surfaced as an unhandled **HTTP 500**
  whenever an admin repeated a name. `slugify()` can also return `''` (a fully Devanagari
  name), so always fall back to a stable non-empty value.
- **Migrations use historical models, which have no overridden `save()`.** A seed
  migration that creates a row with a `slug` field must set that slug **explicitly** in
  `defaults=`, or the row ships with `slug=''`. This actually happened to the seeded vendor.


### URL routing invariants
- `products/urls.py` must keep `path('<slug:slug>/', ProductDetailView, ...)` as the
  **last** public pattern. It was missing entirely at one point, which made the whole
  product detail page 404; it must stay below `featured/`, `categories/`, and `areas/`
  or it will shadow those literal paths.
- Order history is `/api/orders/` and detail is `/api/orders/<id>/`.
  There is **no** `/api/orders/my-orders/`. There is also **no** `/api/products/pujas/`.
- `AdminOrderUpdateView` (`/api/orders/admin/orders/<id>/`) is a **write-only**
  `UpdateAPIView` — `PUT`/`PATCH` only, **no `GET`** (a GET returns 405).
  Read an order back through `/api/orders/<id>/`.
- DRF serializes `DecimalField` as a **string** (`'180.00'`). Cast with `float()` before
  doing arithmetic; `isinstance(price, float)` is `False` on a correct response.


---

## 4. Important directories

```
backend/
  core/settings.py                     Django config (dev values; see Security)
  core/urls.py                         root routing
  core/management/commands/seed_data.py  THE seed command (products/ has a dead duplicate)
  accounts/ products/ festivals/ orders/ analytics/
    models.py serializers.py views.py urls.py admin.py
  media/products/                      product images
  venv/                                virtualenv — run python from here
  db.sqlite3                           the database

frontend/src/
  app/layout.js                        providers + Navbar + Footer
  app/globals.css                      ★ the design system. Tokens + utilities.
  app/page.js                          home (Server Component)
  app/products/          page.js · [slug]/page.js
  app/festivals/         page.js
  app/cart/ · app/checkout/ · app/recommendations/
  app/auth/login/ · app/auth/register/
  app/account/ · app/account/orders/[id]/
  components/Navbar.js · Footer.js
  context/AuthContext.js · CartContext.js · ToastContext.js
  lib/api.js                           ★ single API client — add endpoints here

admin-dashboard/src/
  app/layout.js                        sidebar (role-aware) + AdminProvider
  app/page.js                           dashboard
  app/products/                         product CRUD (create/edit/delete/toggle)
  app/orders/ · app/festivals/ · app/forecast/ · app/settings/ · app/login/
  components/Modal.js                   shared dialog
  components/ConfirmDialog.js           shared destructive-action confirm
  context/AdminContext.js               exposes isAdmin, isManager, role
  lib/api.js
```

★ = the file you will touch most.

---

## 5. Commands

```bash
# Backend — always use the venv interpreter
cd backend
venv/Scripts/python.exe manage.py check
venv/Scripts/python.exe manage.py runserver 8000      # :8000
venv/Scripts/python.exe manage.py makemigrations
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py seed_data           # reseeds admin/…/testuser
venv/Scripts/python.exe manage.py test                # 236 tests
venv/Scripts/python.exe manage.py refresh_festivals   # rebuild the festival calendar
venv/Scripts/python.exe manage.py seed_pujas          # derive rituals from kit/product data
venv/Scripts/python.exe manage.py generate_synthetic_sales   # SYNTHETIC forecast data

# Remove scratch rows left by the verifiers (always run after a verification sweep)
venv/Scripts/python.exe manage.py purge_verification_orders   # --dry-run supported
venv/Scripts/python.exe manage.py purge_verification_users    # --dry-run supported

# Live end-to-end verification (server must already be running on :8000)
venv/Scripts/python.exe verify_day2.py                # 68 assertions
venv/Scripts/python.exe verify_day3.py                # 55 assertions — roles & CRUD
venv/Scripts/python.exe verify_day3b.py               # 41 assertions
venv/Scripts/python.exe verify_day3c.py               # 128 assertions — full shopping flow
venv/Scripts/python.exe verify_day4.py                # 88 assertions — history, reset, validation
venv/Scripts/python.exe verify_day6.py                # 40 assertions — the ritual entry point
venv/Scripts/python.exe verify_day7.py                # 30 assertions — token revocation

# Frontend — :3000
cd frontend && npm run dev
cd frontend && npm run build        # MUST pass before you call anything done

# Admin dashboard — :3001
cd admin-dashboard && npm run dev -- -p 3001
cd admin-dashboard && npm run build

# Catch undefined-variable bugs — the project's ESLint config does NOT enable no-undef,
# so `next lint` stays silent. Four broken buttons once shipped because of this.
npx eslint --rule '{"no-undef":"error"}' src/

# Demo credentials (seeded)
#   admin    / admin123      superuser          → role super_admin
#   vendor1  / vendor1234    vendor account     → role vendor
#   testuser / test1234      customer
```

> **Sandbox note.** `next build` deletes files inside `.next/`. In a sandboxed shell this can be
> blocked by a bulk-delete guard and reported as `Build error occurred`, even though the compile
> itself succeeded (`✓ Compiled successfully`). If you see
> `SAFE_DELETE_BULK_CONFIRM_REQUIRED`, re-run the build with the sandbox disabled, or
> `rm -rf .next` first and rebuild. Always confirm the real result via `EXIT=$?` and the
> `Compiled successfully` line, not just the presence of the word "Error".
>
> **The guard counts deletions per turn**, so once it has tripped, even a later
> `rm -f somelog.txt` in the same turn is refused — and if that `rm` is chained with `&&`, the
> command after it silently never runs. That is how a "failed" build turns out to have never
> executed at all. Prefer a fresh filename over `rm`, and check the log file for a
> `Compiled successfully` line before believing a failure.

> **Stale-server trap — this has cost real time twice.** `runserver --noreload` started in a
> background shell **outlives the shell** if the shell exits abnormally, and keeps the port.
> A second `runserver` then fails to bind while the old process keeps answering with **stale
> code** — producing symptoms that look exactly like a code bug (`404` on a route that exists,
> a missing response key). Before debugging a "missing" endpoint:
> ```bash
> netstat -ano | grep ":8000.*LISTENING"     # find the PID
> # then kill it (taskkill //PID is not valid in Git Bash — use PowerShell)
> ```
> ```powershell
> Stop-Process -Id <pid> -Force
> ```
> Then restart with `run_in_background: true` and confirm with `curl`. Day 3 lost time to a
> stale process serving pre-`Area` code, and Day 2 lost time to the same pattern.
> **`taskkill //PID <n> //F` does not work in Git Bash** — it rejects the double-slash syntax.

**Ports:** backend 8000, frontend 3000, admin 3001.
`frontend/src/lib/api.js` reads `NEXT_PUBLIC_API_URL`, defaulting to `http://127.0.0.1:8000/api`.
`admin-dashboard/src/lib/api.js` reads the same env var.

### Delivery fee
`DELIVERY_FEE` lives in `core/settings.py` and is the **only** place it is defined.
It is exposed publicly via `GET /api/orders/config/` and persisted per-order in
`Order.delivery_fee`. Both frontends read it from the API.
**Never hardcode the delivery amount in a component** — that is the bug that made the cart
promise Rs. 100 more than the order recorded.

### Never hardcode a list the database already holds

Three hardcoded lists each hid real data, and none of them failed loudly — they silently
made the unlisted thing unreachable:

| Was hardcoded | Now |
|---|---|
| `CITY_CHOICES` in three files | The `Area` table (Day 3) |
| The festival type filter in `festivals/page.js` (seven literals) | Derived from the kits' own `festival_type` / `festival_type_display` (Day 5) |
| `/festivals/upcoming/` capped at `[:5]` | `?limit=`, default 5, max 50 (Day 5) — five of ten active festivals had been unreachable |

**If a value is a row in the database, read it. Do not write it into a component.**

### One product tile

`frontend/src/components/ProductCard.js` is the **only** product tile — home, catalogue and
recommendations all render it. They previously had three implementations that had drifted,
and the home version's `+` button had **no handler at all**: it looked like an add-to-cart
control and did nothing.

It is a client component, because the add button needs the cart context. It reads that
context itself rather than accepting a callback, so the Server Component home page can render
it without passing a function across the boundary. Optional `reason` and `badge` props carry
the recommendation explanation and the festival-urgency label.

**Do not hand-roll a fourth variant.** Adding one is exactly how the first three drifted apart.

---

## 6. Database rules

1. **Inspect before you migrate.** Read `models.py` and the existing `migrations/` first.
2. **Reuse existing tables.** Do not create a parallel model for something that exists.
3. **`OrderItem` is a historical record.** Never add a migration that would rewrite past orders.
4. **Additive migrations only** unless you have explained the impact and got approval.
   No dropping columns or tables that hold seeded data.
5. Migrations must be committed with the model change in the same change set.
6. **`upcomingfestival.date` drives the whole prediction story.** Seed realistic future dates
   relative to *today* — hardcoded past dates silently disable the recommendation and alert logic.
7. Run `makemigrations` then `migrate`, then `manage.py check`, before declaring DB work done.
8. **Never use `auto_now_add` on a field a data migration needs to backfill.** `auto_now_add`
   silently discards any value passed to the constructor, so a backfill cannot preserve a real
   historical timestamp. Use `default=timezone.now` — that is why `OrderStatusEvent.created_at`
   is written that way. (Same family of trap as a historical model having no overridden `save()`.)
9. **Money and quantity fields need a lower bound.** `Product.price` and `Area.delivery_fee`
   carry `MinValueValidator(0)`. A negative price subtracts from the cart; a negative delivery
   fee means the store pays the customer. DRF copies model validators onto serializer fields, so
   a validator on the model covers both the API and the Django admin.
10. **Uniqueness the model cannot express belongs in the serializer.** `Category.name` is checked
    case-insensitively in `CategoryAdminSerializer.validate_name`. The slug suffixer in
    `Category.save()` must stay as the last-resort net — it exists because a duplicate slug was
    an unhandled `IntegrityError` (HTTP 500) — but it must never be the *only* guard, or a
    duplicate name is silently filed as `name-1` and one category becomes two.

**`CITY_CHOICES` now lives only in `core/constants.py`** (Day 3). `Area` rows superseded it for
delivery; import the constant rather than adding another copy.

**`seed_data` exists twice** — `core/management/commands/` and `products/management/commands/`,
byte-identical. Only `core`'s runs. If you change seeding, change `core`'s; delete the other.

---

## 7. Authentication rules

- JWT via SimpleJWT. Access 1 day, refresh 7 days, rotation on.
- Login is **username + password**. Register collects email.
- Password hashing is Django's — always `create_user` / `set_password`. **Never** `User(...)`
  with a raw password.
- Never log, return, or serialize a password or token in an API response.
- Both frontends keep the token in `localStorage` and attach `Authorization: Bearer <token>`.
- `frontend/src/lib/api.js` auto-refreshes on 401 and retries once. Preserve that behaviour.
- **A frontend page must never call the API during render if it needs a token.**
  `lib/api.js` reads `localStorage`, which does not exist server-side. Use `useEffect`
  (client component) for authenticated calls. Public catalog data may be fetched in a
  Server Component — but not with the fallback-masking pattern described in §11.

**Demo-auth gap, known and accepted:** there is no email login, OTP, or password reset.
The brief permits a safe demo mechanism. If you add password reset, implement it as a real
token flow and clearly flag it as demo-grade — do **not** fake a successful reset.
---

### Token revocation *(added Day 7)*

JWTs are stateless, so nothing can un-issue one. `SIMPLE_JWT`'s access tokens last a day,
which meant a password reset left any stolen token working for up to 24 hours — a limitation
this project documented rather than fixed. It is fixed now:

- Every token carries the user's current `UserProfile.token_version` as the `tv` claim.
- `accounts.tokens.VersionedJWTAuthentication` (the project's `DEFAULT_AUTHENTICATION_CLASSES`)
  compares that claim against the stored value **on every authenticated request** and rejects a
  mismatch with a 401.
- `accounts.tokens.VersionedTokenRefreshSerializer` does the same at `token/refresh/`. **This is
  not optional**: the refresh endpoint never goes through DRF's authentication classes, so
  without it a revoked refresh token keeps returning 200 and minting access tokens.
- `revoke_tokens(user)` bumps the version. It is called by password reset and by
  `POST /api/auth/logout-all/`.
- Tokens minted before this existed carry no claim and read as version 0, matching the default,
  so deploying it does not sign anyone out.

**Do not swap `DEFAULT_AUTHENTICATION_CLASSES` back to the stock `JWTAuthentication`, and do not
route `login/` or `token/refresh/` at the stock SimpleJWT views.** Either change silently
disables revocation — nothing fails, the tests just stop protecting anything.

**Why not `token_blacklist`?** That app blacklists *refresh* tokens only, so the access token
derived from one keeps working until its own expiry. The threat here is precisely the
outstanding access token.

**Known limit, stated plainly:** a bump invalidates tokens, not sessions that never had one. A
user's password hash changing does not by itself revoke anything — `revoke_tokens` has to be
called.

## 8. Authorization rules

**The role system lives in `backend/core/permissions.py`. It is the single source
of truth. Do not write a new `user.is_staff` check anywhere.**

### The four roles

```
SUPER_ADMIN  →  everything
     ↓
   ADMIN     →  catalogue, kits, orders, vendors, areas
     ↓
   VENDOR    →  only their own products, and the orders containing them
     ↓
  CUSTOMER   →  own cart, own orders
```

### Resolution order — this order is load-bearing

`get_role()` resolves in **exactly** this precedence:

1. `is_superuser` → `super_admin`
2. explicit `profile.role` (if not `customer`) → that role
3. `is_staff` → `admin`
4. otherwise → `customer`

> **Why step 2 precedes step 3.** A vendor account is necessarily `is_staff` (it
> needs to reach the API). On Day 3 the check was written the other way round, so
> `vendor1` resolved to **`admin`** and got the entire catalogue. The bug was
> silent — nothing errored, the vendor simply saw everything. If you reorder
> these steps, `core/tests_roles.py::RoleResolutionTests` will fail.

### Helpers and classes

| Name | Purpose |
|---|---|
| `get_role(user)` | The resolved role string, or `None` if anonymous |
| `is_staff_role(user)` | super_admin / admin / vendor |
| `is_manager(user)` | super_admin / admin |
| `is_super_admin(user)` | super_admin only |
| `is_vendor(user)` | vendor only |
| `vendor_for(user)` | The user's `Vendor` row, or `None` |
| `IsStaffRole` | Any staff role may pass |
| `IsManagerOrReadOnly` | Staff may read; only managers may write |
| `IsSuperAdmin` | Super admin only |
| `IsOwnerVendorOrManager` | Object-level: a vendor may only touch their own object |

### Rules

1. **Vendor scoping goes in `get_queryset()`, not in the UI and not in a
   permission class.** A vendor requesting another vendor's object must get
   **404**, not 403 — they should not be able to confirm it exists.
   ```python
   def get_queryset(self):
       qs = Product.objects.select_related('category', 'vendor')
       if is_manager(self.request.user):
           return qs
       vendor = vendor_for(self.request.user)
       return qs.filter(vendor=vendor) if vendor else qs.none()
   ```
2. **Return `qs.none()`, never an unfiltered queryset, when a vendor has no
   vendor row.** Fail closed.
3. **Never trust a vendor-supplied `vendor` field.** `perform_create()` must
   force ownership for vendors. Covered by
   `test_vendor_created_product_is_attributed_to_them`.
4. **A filter parameter is not a permission bypass.** `?vendor=<other-id>` must
   return `[]` for a vendor, not another vendor's rows. Covered by
   `test_vendor_cannot_probe_via_vendor_filter`.
5. **`role` is read-only in every serializer.** A customer must not be able to
   PATCH themselves into an admin. Covered by `RoleEscalationTests`.
6. **Hide, don't just disable.** Manager-only nav items are filtered out for
   vendors (`NAV_ITEMS.managerOnly` in `admin-dashboard/src/app/layout.js`), and
   manager-only pages render an explanatory panel rather than a broken table.
   This is UX; the server check is the actual boundary. Do both.
7. **Never bypass a permission class to make the demo work.** No `AllowAny` on
   admin views. No "temporarily comment out the check."
8. Public catalogue, kit and recommendation reads stay `AllowAny`. Scoping must
   **not** leak into the storefront — customers buy across vendors.

---

## 9. UI/UX rules

### The design system already exists — use it
`frontend/src/app/globals.css` defines the whole system. **Read it before writing styles.**

```
Colours   --primary  #C41E3A crimson   --secondary #D4A843 gold   --accent #FF6B35
Surfaces  --bg-primary #FFF8F0   --bg-secondary #FFF1E6   --bg-card #FFFFFF   --bg-dark #1A1A2E
Text      --text-primary #1A1A2E  --text-secondary #4A4A6A  --text-muted #8A8AAA
Spacing   --space-xs..3xl      Radius  --radius-sm..full      Shadow --shadow-sm..xl
Motion    --transition-fast .15s  --transition-normal .3s  --transition-slow .5s
Fonts     --font-heading 'Outfit'   --font-body 'Inter'
```

Global utilities — **already defined, do not re-implement per page**:
`.container .section .section-title .section-subtitle .bg-dark .bg-secondary`
`.btn .btn-primary .btn-secondary .btn-outline .btn-sm .btn-lg .btn-icon`
`.card .badge .badge-{primary,secondary,success,warning,danger}`
`.grid .grid-2 .grid-3 .grid-4`
`.form-group .form-label .form-input .form-select`
`.skeleton .animate-fadeInUp .animate-fadeIn .animate-slideIn .toast .toast-{success,error,info}`

### Rules
1. **Page-specific CSS goes in that route's `*.module.css`.** Never add a global rule for one page.
2. **Never hardcode a hex colour.** Use a token, so re-theming stays possible.
3. **Reuse before you rebuild.** Inspect the screen, reuse its components, then improve.
   Only redesign a page that is genuinely broken.
4. Product cards must be consistent across home / products / recommendations / category pages.
   The product card markup is duplicated today — if you touch it, extract one component rather
   than editing four copies.
5. Every async surface needs **four** states: **loading · success · empty · error.**
   Skeletons already exist (`.skeleton`). Never leave a blank screen.
6. **Never show a raw stack trace, SQL error, exception string, or internal path to a user.**
   `frontend/src/lib/api.js` currently does `JSON.stringify(error)` as a fallback message —
   replace that with a generic human message.
7. Responsive is required at desktop / tablet / mobile. `globals.css` already collapses
   `.grid-4`→3→2→1. Do not merely shrink the desktop layout; check the navbar, product grid,
   forms, cart, checkout, dashboard tables and modals.
8. Accessibility: keep contrast AA, keep focus visible, label every input, give icon-only
   buttons an `aria-label` (the `+` add-to-cart button needs one).

### Animation rules
Subtle, fast, purposeful, performant. Animations are **already in place** — extend, don't pile on.
- Allowed: fade/slide entrance, hover lift on cards, button feedback, modal transition,
  skeleton shimmer, toast slide-in, cart badge.
- Forbidden: animating every element, long transitions (>~400ms), bounce for its own sake.
- Wrap any new motion in `@media (prefers-reduced-motion: reduce)` to disable it.

---

## 10. AI/ML rules

Two separate features. **Do not merge them. Do not fake either.**

### Recommendation ✅ implemented
- **Implementation:** `backend/festivals/recommender.py` → `Recommender.build()`.
  The view `RecommendationsView` only does HTTP + serialization. **Put new ranking logic in
  `Recommender`, never in the view** — that is what makes it unit-testable.
- Must stay **ranked and explainable.** Every recommended product carries `reasons[]`, each with
  `code` + `points` + human-readable `text`.
- Weights live in `WEIGHTS` (one dict). If you change a weight, update
  `docs/AI-RECOMMENDATION.md` §2 — the doc quotes the numbers verbatim.
- Current signals: `festival_required` 60 · `festival_optional` 30 · `staple_samagri` 28 ·
  `user_category` 22 · `user_kit_affinity` 16 · `user_repeat` 14 · `popular` 8–12.
- **Never return a `set()`.** A `set` destroys ordering — this was the original bug. The sort
  key ends in `product.id` so ordering is fully deterministic; there is a test for it.
- **Cold-start is the normal case** (8 orders total). Anonymous visitors get festival +
  popularity; personalisation only activates when history exists, and the response says so via
  `meta.personalised`.
- `staple_samagri` exists because kitless festivals (e.g. Ganesh Chaturthi, `festival_type='other'`)
  would otherwise be invisible. It is **capped below** `festival_required` on purpose.

### Demand prediction ✅ implemented
- **Implementation:** `backend/analytics/forecasting.py` → `SeasonalForecaster`.
  Endpoint `GET /api/analytics/demand-forecast/` (admin only). Doc: `docs/AI-PREDICTION.md`.
- Model: `level × weekday_factor × festival_factor × damped_trend`. Hand-written stdlib only.
  **Do not add scikit-learn / numpy / pandas** — the dependency cost is not justified.
- **The training data is SYNTHETIC** (14,000 rows, 35 products, 400 days, fixed seed).
  Real history is 8 orders across 9 days — far too thin to train on.
- The synthetic flag must appear in **three** places, and tests assert all three:
  1. the row (`.is_synthetic = True`),
  2. the API response (`data_source: "synthetic"`, `is_synthetic: true`, `provenance_note`),
  3. the UI (warning banner at the top of `/forecast`).
- **Never present synthetic data as real demand.** Do not remove the banner or the flags.
- Report an **honest holdout metric**. Currently mean MAPE 26.20 % over a 28-day holdout,
  MAE 0.810 vs naive 0.936 (+13.5 %). Do not inflate these numbers.
- Regenerate the dataset with `python manage.py generate_synthetic_sales --purge`
  (deterministic — a fixed seed means regeneration is byte-identical).


### Global
- No fake AI. A button that shows random products or a hardcoded alert is worse than no feature.
- No API keys in source. If a model is precomputed, commit the artifact + the training script.
- Keep model inference fast enough to serve on request (or precompute and cache it).

---

## 11. Coding conventions

**Backend**
- API-first. Views are DRF generics/`APIView`; business logic stays in the view or a helper —
  do not build a heavyweight service layer.
- Serializers own shape. Public read serializers are separate from admin serializers
  (`ProductListSerializer` vs `ProductAdminSerializer`) — keep that split.
- Match the existing style: `permission_classes` explicit on **every** view, even `AllowAny`.
- Never write an N+1 query. Use `select_related` / `prefetch_related` as the existing code does,
  and use `aggregate`/`annotate` for totals instead of looping in Python.
- Return errors as JSON with a stable shape (`{'error': '...'}`), as `orders/views.py` does.
- Wrap multi-write operations in `transaction.atomic` — `CheckoutView` already does; follow it.

**Frontend**
- App Router. `'use client'` only when you need state, effects, or events.
- `useSearchParams()` **must** be inside `<Suspense>`. `festivals/page.js` shows the correct
  pattern — copy it for `auth/login` and `auth/register`.
- No `router.push()` during render. Use `useEffect`. (`checkout/page.js` currently violates this.)
- All API calls go through `lib/api.js`. Add a method there; never inline a raw `fetch` in a page.
- Use `next/link` for navigation, `next/image` or a sized `<img>` for images.
- Use the `useToast()` context for user feedback. Do not use `alert()`/`confirm()` for anything
  new (the cart's `window.confirm` is legacy).
- Prefer small focused components; extract when markup repeats more than twice.

**General**
- Delete dead code rather than commenting it out.
- No `console.log` in committed code (`console.error` in a `catch` is fine).
- Leave the code readable. No clever one-liners.

---

## 12. Testing rules

**Test after every feature — not at the end.**

Minimum loop for any change:
1. `manage.py check` (backend) or `npm run build` (frontend) — must be clean.
2. Run it, hit the actual endpoint/page.
3. Test the happy path **and** the failure path (bad input, no stock, wrong role).
4. Confirm you did not break a neighbour (cart, auth, existing pages).
5. Fix regressions before moving on.

**Always re-verify these, they are the demo:**
- E2E: home → category/festival → product → add to cart → cart → checkout → order history.
- Login as `admin`, `vendor1`, `testuser`; confirm a customer is refused on every admin
  endpoint (403) and a vendor is confined to their own rows.
- Checkout with an empty cart and with over-stock quantity → proper errors, no 500.
- `frontend` and `admin-dashboard` production builds both pass.

**Record for each completed P0 feature:** feature · test performed · result · known limitation.
Keep it in `docs/CURRENT-STATE.md`.

Django tests live in `backend/<app>/tests.py` plus `backend/core/tests_roles.py`.
There are now **236**, covering the recommender (30), the forecaster (33), the
role/scoping system (47), order status history (23), password reset (25),
catalogue validation (17), the Puja entry point (24), add-puja-to-cart (10) and
token revocation (17). Live suites cover the rest:

| Suite | Assertions |
|---|---|
| `verify_day2.py` | 68 |
| `verify_day3.py` | 55 |
| `verify_day3b.py` | 41 |
| `verify_day3c.py` | 128 |
| `verify_day4.py` | 88 |
| **Total live** | **380** |

**After any verification sweep, purge what it created** — `purge_verification_orders`
and `purge_verification_users`, both with `--dry-run`. A verifier that leaves rows
behind makes the demo order ids drift and can leave a stray login on the system.

> **Test the thing, not its shape.** When the recommender was rebuilt on Day 2, the
> old tests passed against a broken implementation because they only asserted the
> *shape* of the response, not the ordering or the explanation. Write assertions
> that fail when the feature is wrong.
>
> The Day 4 password-reset suite is the worked example: "returns 200" passes against
> an endpoint that does nothing. The tests assert that the new password actually
> authenticates through `/login/`, that the old one no longer does, and that a
> second use of the same link is refused.

> **Beware pagination in assertions.** `len(response.json())` on a DRF paginated
> body returns **4** (the number of keys), not the record count. This produced two
> false "failures" on Day 3. Unwrap `results`, and follow `next` when you need a
> true total (`verify_day3.py::count_all` shows the pattern).

---

## 13. Security rules

- **No secrets in source.** `settings.py` currently hardcodes `SECRET_KEY` and seeds use
  `admin123`/`test1234`; move real config to environment variables when you touch settings.
- `DEBUG = True`, `ALLOWED_HOSTS = ['*']`, `CORS_ALLOW_ALL_ORIGINS = True` are **dev-only and
  must not ship**. Narrow them before any real deployment.
- **Remove the hardcoded credentials from `admin-dashboard/src/app/login/page.js`** — the form
  currently pre-fills `admin`/`admin123` as defaults.
- Validate and bound every input server-side: quantity ≥ 1, price never trusted from the client,
  `shipping_city` restricted to the allowed set (already done). Never accept a client-supplied
  total.
- Never trust a client-supplied user id, role, or price on any write endpoint.
  **`role` must stay read-only in every serializer** — a customer who can PATCH their own role
  is a total compromise. Covered by `RoleEscalationTests`.
- **Vendor ownership is server-derived.** Never persist a `vendor` value that came from a
  vendor's own request body; use `perform_create()` to force it.
- File uploads (product/kit images) must be type- and size-checked; never serve a user-controlled
  path.
- DRF + ORM parameterization handles SQL injection by default — **keep using the ORM.**
  Do not introduce raw SQL with string interpolation.
- Do not commit `db.sqlite3` or `media/` in future commits; they are currently tracked.
- Image upload fields are open in the admin serializers (`fields = '__all__'`) — ensure upload
  endpoints stay behind an admin permission.
- The admin dashboard's client-side gate (`AdminContext` + `AuthGate`) is a **UX guard, not a
  security boundary**. Never rely on it alone.
- **`PASSWORD_RESET_EXPOSE_LINK` must be `False` anywhere real.** It defaults to `DEBUG`, and it
  returns a working reset link in the API response so the flow can be demoed without a mailbox.
  A link can only exist for a real account, so returning it **is** account enumeration. It is
  asserted to leak exactly two fields and no more; the production configuration is asserted
  separately to be byte-identical for known and unknown addresses.
- **Password-reset endpoints never reveal whether an address is registered.** Same status, same
  wording, and a bad uid is indistinguishable from a bad token. A mail-delivery failure is logged
  rather than surfaced, because a 500 only happens when an account matched.
- **Password reset DOES revoke existing JWTs** (Day 7) — via the token version claim, not a
  blacklist. Keep `DEFAULT_AUTHENTICATION_CLASSES` and the login/refresh routes pointed at the
  versioned classes in `accounts.tokens`, or revocation silently stops working. See §7.
- **Bound money fields server-side.** `Product.price` and `Area.delivery_fee` carry
  `MinValueValidator(0)`; a negative delivery fee means the store pays the customer.
- **Never put a destructive call in a verifier's cleanup.** A stray `DELETE` once removed a
  seeded product. Confirm a row is one the script created before deleting it, or mark it and use
  a purge command.
- **Check for undefined identifiers when adding UI.** The ESLint config does not enable
  `no-undef`, so a typo'd state setter builds and lints clean and only fails on click — four
  buttons in Catalog Settings shipped broken that way. Run
  `npx eslint --rule '{"no-undef":"error"}' src/` in both frontends.

---

## 14. Current priorities

Full detail in `docs/CURRENT-STATE.md` §Priority. Summary:

**P0 — finish before anything else**
1. ~~Fix the `frontend` production build~~ ✅ **Day 1**
2. ~~Delivery fee must actually be in `Order.total_amount`~~ ✅ **Day 1**
3. ~~Admin dashboard: real APIs, restore the login gate, stop faking data on error~~ ✅ **Day 1**
4. ~~Real ranked/explainable recommendation engine~~ ✅ **Day 2**
5. ~~Demand prediction: data → trained model → endpoint → admin UI~~ ✅ **Day 2**
6. ~~Vendor role + vendor product management~~ ✅ **Day 3**
7. ~~`Area` model + area management; Super Admin vs Admin split~~ ✅ **Day 3**
8. ~~Admin CRUD write actions (products, categories, areas)~~ ✅ **Day 3**
9. ~~Order tracking; responsive polish; four-state audit~~ ✅ **Day 3.4**
10. ~~Full demo rehearsal~~ ✅ **Day 3.4** — automated as
    `backend/verify_day3c.py` (128 assertions, covers the whole purchase path)
11. ~~Route the product detail endpoint~~ ✅ **Day 3.4** — it was missing; the shop's
    "View details" button 404'd on every click

**All P0 items are closed.** Remaining known gaps are P1/P2 only (see `docs/FEATURES.md`
§ "What is NOT built"). Before adding anything, re-run the full verification sweep:

```
./venv/Scripts/python.exe manage.py test          # 236 unit tests
./venv/Scripts/python.exe verify_day2.py          # 68 assertions
./venv/Scripts/python.exe verify_day3.py          # 55 assertions
./venv/Scripts/python.exe verify_day3b.py         # 41 assertions
./venv/Scripts/python.exe verify_day3c.py         # 128 assertions
./venv/Scripts/python.exe verify_day4.py          # 88 assertions
./venv/Scripts/python.exe manage.py purge_verification_orders   # clean up after
./venv/Scripts/python.exe manage.py purge_verification_users
```

**Day 4 — trust & honesty pass (2026-09-19)** closed the gaps the docs themselves admitted to:
real order-status timestamps (`OrderStatusEvent`), a real password reset flow, per-field admin
validation, three data-integrity holes (negative price, negative delivery fee, duplicate category
name), a completely broken Catalog Settings page, and the fact that **nothing was under version
control**. 178 unit tests + 380 live assertions pass.

**P1** wishlist · reviews/ratings · vendor self-service UI · kit editor UI · vendor & area
analytics · search relevance · image upload widget · JWT revocation on password reset

**P2** live payments · notifications · advanced analytics · extra animation

**Day 5 — the festival domain, made visible (2026-09-19)** rebuilt the home page to lead with
the next festival and its required samagri, replaced three drifted product cards with one
shared `ProductCard`, and removed two more hardcoded lists. 185 unit tests + 380 live
assertions pass.

**The shopping flow already works.** Do not rebuild it. Fix, extend, and polish.

---

## 15. Do not unnecessarily change

These are working and load-bearing. Improve around them; do not rewrite them.

- **The database schema.** 35 products, 10 categories, 7 kits, 68 kit items, 5 festivals and
  8 orders are already seeded and coherent. Additive changes only.
- **The six public endpoint URLs** in `core/urls.py`. Both frontends depend on them.
- **`globals.css` and the CSS-module approach.** The token system is good. Extend it.
- **The split serializer pattern** (public vs admin) in `products`/`festivals`.
- **The `accounts` / `products` / `festivals` / `orders` / `analytics` app split.**
- **`analytics` having no models** — plain aggregation is the right design here.
- **`OrderItem`'s `product_name` + `price` snapshot.** Orders must survive price changes.
- **`KitItem.is_required`** — it is the required-samagri mechanism.
- **The JWT + 401-refresh logic in `frontend/src/lib/api.js`.**
- **The React Context providers** (`Auth`, `Cart`, `Toast`) and the `layout.js` composition.
- **`FestivalKit.total_price` / `original_price`** as model properties.
- **The `transaction.atomic` checkout.** Stock decrement and order creation must stay atomic.
- **Two separate frontends.** The customer storefront and the admin panel are deliberately
  different apps with different auth. Do not merge them.

**Before any destructive or architectural change:** check `git status` in the affected
subproject, confirm what is uncommitted, and do not overwrite working code with a rewrite.

---

## 16. Working agreement

Work in the order **inspect → plan the smallest correct change → implement → test → fix →
update docs**. Do not generate large amounts of untested code.

When several implementations are possible, choose the one that is: compatible with what exists,
fast to finish, stable, easy to demo, maintainable, and proportionate to a final-year project.
A simpler correct solution beats a sophisticated unverifiable one.

Keep docs current as you go: `AGENTS.md`, `README.md`, `docs/CURRENT-STATE.md`,
`docs/FEATURES.md`, `docs/DATABASE-DESIGN.md`, `docs/API-SPEC.md`, `docs/AI-RECOMMENDATION.md`,
`docs/AI-PREDICTION.md`, `docs/UI-UX-SPEC.md`, `docs/DEVELOPMENT-ROADMAP.md`.
Short and accurate beats long and stale.
