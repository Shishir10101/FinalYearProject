# AGENTS.md

Permanent instruction file for coding sessions on this repository.
Written from the actual codebase — every path, model, and command below was verified.

**Read `docs/CURRENT-STATE.md` first.** It holds the live status of what works, what is
broken, and what is missing. This file holds the rules for changing it.

---

## 1. Project purpose

An Online **Puja Sewa** e-commerce platform for **Kathmandu Valley**
(Kathmandu, Lalitpur, Bhaktapur), Nepal.

The store trades as **Puja Sewa**; **puja samagri** is what it sells (the merchandise
category, and the name of one of the six discovery entry points below). Do not conflate
the two — a rebrand must not rename the domain concept.

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
>
> **This is live in this project, not hypothetical.** `/pujas/[slug]` calls `notFound()` for an
> unknown ritual and returns **200**, because `src/app/pujas/loading.js` opens a Suspense
> boundary — verified with `curl -o /dev/null -w '%{http_code}'`. Two comments used to claim it
> returned a real 404. If you need a genuine 404 status on a route, the `loading.js` has to go,
> and the loading skeleton is usually worth more than the status code. **Assert the
> user-visible behaviour and the `noindex`; do not assert `status === 404` on a streamed route.**

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
- **`WishlistItem`** (Day 13) is one row per `(user, product)`, with `product` as **`CASCADE`** —
  the opposite of `OrderItem`'s `SET_NULL` + snapshot, and deliberately so: a wishlist row is a
  pointer to something you intend to buy, so if the product goes there is nothing left to save,
  whereas an order is a record of a past transaction that must outlive the product.
  `POST /api/products/wishlist/` is create-or-**get**, because the control that calls it is a
  toggle and a double-clicked heart must not be a `400`.
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
- **`Puja` cannot be given a kit through its own API.** The FK is on the kit
  (`FestivalKit.puja`) — a kit declares which ritual it serves, and one ritual may have several
  bundles, so a singular write field on `PujaAdminSerializer` would have to pick one arbitrarily.
  `kit_names` / `kit_count` are read-only reports. Set the link from the kit endpoint.
- **`FestivalKitAdminSerializer` lists its fields explicitly, not `fields = '__all__'`.** It
  carries a declared `item_count` the dashboard table needs, and `image` is deliberately
  excluded — it is a file upload, and a JSON form posting a string path to it would get a
  validation error for a field it never rendered. Adding a model field will not silently expose
  it here; add it on purpose.
- **Both item list endpoints return a bare array and are unpaginated.** `PAGE_SIZE` is 12,
  Bratabandha has 14 items, Daily Puja has 21. Tests assert a bare list because a `results`
  dict would still pass a `len()` check against a page. Do not "fix" them to match the others.
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
- The rule is stronger than "the slug route goes last": **nothing with a slug converter may sit
  above a literal path of the same depth.** `<slug:slug>/reviews/` matched `admin/reviews/` with
  `slug='admin'` and 404'd that entire API. `wishlist/` (Day 13) is a valid slug too, so it sits
  with the other public literals. Adding a route? Put it with its family, never above the slug
  patterns.
- `festivals/urls.py` nests its slug pattern under a prefix (`pujas/<slug:slug>/`), so
  it cannot shadow the literal `pujas/` — unlike the flat `products/urls.py` case above.
  Keep it that way.
- Admin kits and rituals are parallel URL families that must stay parallel:
  `/admin/kits/` ↔ `/admin/pujas/`, `/admin/kits/<id>/items/` ↔
  `/admin/pujas/<id>/items/`, `/admin/kit-items/<pk>/` ↔ `/admin/puja-items/<pk>/`.
  The dashboard drives both from one component, so a divergence here breaks the editor
  for one domain only — the kind of bug that survives a smoke test of the other.
- Order history is `/api/orders/` and detail is `/api/orders/<id>/`.
  There is **no** `/api/orders/my-orders/`. There is also **no** `/api/products/pujas/`.
  Rituals live at `/api/festivals/pujas/`.
- **`/api/auth/profile/` implements `PUT`, not `PATCH`.** A `PATCH` returns 405, and two
  "role is read-only" guards once passed against exactly that without testing anything.
  `/api/accounts/...` does not exist — the prefix is `auth`.
- The account picker is `/api/auth/admin/users/`, under the `auth` prefix because it is
  about accounts, not the catalogue.
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
  products/search.py                   ★ domain-aware search (synonyms, domain index, scoring)
  festivals/recommender.py             ★ explainable recommendation ranker
  analytics/forecasting.py             ★ demand forecaster (stdlib only)
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
venv/Scripts/python.exe manage.py test                # 498 tests
venv/Scripts/python.exe manage.py refresh_festivals   # rebuild the festival calendar
venv/Scripts/python.exe manage.py seed_pujas          # derive rituals from kit/product data
venv/Scripts/python.exe manage.py generate_synthetic_sales   # SYNTHETIC forecast data

# Demo imagery — fetches freely-licensed photos from Wikimedia Commons, crops them
# square and re-encodes to 600x600 JPEG q82 (~40-70 KB, versus ~700 KB before), and
# writes attribution to media/IMAGE-CREDITS.md. Never leaves a row without an image:
# anything it cannot find gets a locally drawn tile carrying the item's name.
#   Commons rate-limits (429) — it backs off and retries; --retry-fallbacks re-tries
#   only the rows that still hold a tile. --match "<substring>" re-fetches one row.
#   A wrong photo is worse than a tile, so near-miss titles are rejected by keyword
#   (Commons returns *conch fritters* for "conch shell", *coconut cookies* for
#   "dried coconut"). Verify the result by LOOKING at it, not by counting files.
venv/Scripts/python.exe manage.py fetch_demo_images          # products+categories+kits
venv/Scripts/python.exe manage.py fetch_demo_images --force  # re-fetch everything
venv/Scripts/python.exe manage.py fetch_demo_images --retry-fallbacks
venv/Scripts/python.exe manage.py fetch_demo_images --match "Kalash,Bell"
venv/Scripts/python.exe manage.py fetch_demo_images --dry-run

# Remove scratch rows left by the verifiers (always run after a verification sweep)
venv/Scripts/python.exe manage.py purge_verification_orders   # --dry-run supported
venv/Scripts/python.exe manage.py purge_verification_users    # --dry-run supported
venv/Scripts/python.exe manage.py purge_verification_reviews  # --dry-run supported

# Live end-to-end verification (server must already be running on :8000)
#   Run the server with --noreload for a sweep. Editing any .py in backend/ makes the
#   autoreloader restart the child, and a child that dies mid-reload leaves the parent
#   holding :8000 and answering nothing (curl exits 56 with an empty body). That looks
#   exactly like a broken endpoint. If it happens: kill the listener, restart.
venv/Scripts/python.exe verify_day2.py                # 68 assertions
venv/Scripts/python.exe verify_day3.py                # 57 assertions — roles & CRUD
venv/Scripts/python.exe verify_day3b.py               # 41 assertions
venv/Scripts/python.exe verify_day3c.py               # 129 assertions — full shopping flow
venv/Scripts/python.exe verify_day4.py                # 88 assertions — history, reset, validation
venv/Scripts/python.exe verify_day6.py                # 40 assertions — the ritual entry point
venv/Scripts/python.exe verify_day7.py                # 30 assertions — token revocation
venv/Scripts/python.exe verify_day8.py                # 74 assertions — kit & ritual authoring
venv/Scripts/python.exe verify_day9.py                # 49 assertions — vendor administration
venv/Scripts/python.exe verify_day11.py               # 68 assertions — reviews & moderation
venv/Scripts/python.exe verify_day12.py               # 84 assertions — search & ranking
venv/Scripts/python.exe verify_day13.py               # 68 assertions — wishlist, uploads, areas
venv/Scripts/python.exe verify_day14.py               # 21 assertions — mocked-payment disclosure

# Real-browser checks (dashboard on :3001, storefront on :3000, API on :8000).
# These are the ONLY checks that can see a client-side render failure: `AuthGate`
# renders "Checking your session…" during SSR, so curl gets a healthy 200 with an
# empty shell. They drive the Edge already on the machine via playwright-core, so
# there is no Chromium download and nothing is added to package.json. One-time setup:
#   mkdir -p /tmp/harness && cd /tmp/harness && npm init -y && npm install playwright-core
#
# ON WINDOWS, NODE_PATH MUST BE A WINDOWS PATH. Node resolves NODE_PATH itself and does
# not understand Git-Bash's /tmp mount, so `/tmp/harness/node_modules` fails with
# `Cannot find module 'playwright-core'` although the package is installed. Resolve it
# once with `pwd -W` inside the harness directory (here it is
# C:\Users\dell\AppData\Local\Temp\harness\node_modules) and use that.
#   Windows:  NODE_PATH='C:\Users\<you>\AppData\Local\Temp\harness\node_modules'
#   Linux/mac: NODE_PATH=/tmp/harness/node_modules
# SHOT_DIR must be a Windows path for the same reason.
cd admin-dashboard
NODE_PATH=<harness>/node_modules node scripts/browser_check.mjs      # 119 assertions
cd ../frontend
NODE_PATH=<harness>/node_modules node scripts/storefront_check.mjs   # 136 assertions
# The storefront check places ONE real order; clean it up with
#   cd backend && venv/Scripts/python.exe manage.py purge_verification_orders
# The dashboard check seeds one review through the API and removes it again; the
# storefront check posts one and deletes it through the UI. If either is interrupted
# mid-section: manage.py purge_verification_reviews
#
# Scroll smoothness (needs the storefront on :3000, production build):
NODE_PATH=<harness>/node_modules node scripts/scroll_probe.mjs
# It scrolls the whole page in a real browser and counts frames over 50 ms, and also
# reports broken/relative <img> sources. Baseline: 0 long frames of 354, worst ~22 ms,
# 0 broken, 0 relative. Neither the unit tests nor storefront_check.mjs can see a
# scroll regression — they assert content, not smoothness — so this is the only check
# standing behind the four jank fixes (sticky-bar backdrop-filter, infinite pulse,
# unpromoted rotating hero circles, eager ~700 KB images).
#
# Run them against a PRODUCTION build (`npm run build && npx next start -p <port>`),
# not `next dev`. Under `next dev` the HMR websocket fails in the sandbox and the
# client never hydrates: every page renders its SSR shell and no card ever appears,
# so the harness fails on a page that is perfectly healthy. A production build has no
# HMR socket. If you do use dev, pre-warm every route with curl first — Turbopack's
# first compile of a route can exceed the harness's 25s selector timeout.
#
# Start the two frontends SEQUENTIALLY, pinned: `next dev` with no `-p` races for
# :3000 and the loser silently takes :3001. The storefront then serves on the admin's
# port and both harnesses point at the wrong app.

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
> itself succeeded (`✓ Compiled successfully`). Always confirm the real result from the log's
> `Compiled successfully` / `Generating static pages (N/N)` lines and the compiled manifest
> (`.next/app-path-routes-manifest.json`), not from `EXIT=$?` and not from the word "Error".
>
> There are two distinct modes, and they need opposite responses:
>
> 1. **Guard fires at the END** — the log contains `✓ Compiled successfully` and
>    `✓ Generating static pages (N/N)` above the error. Turbopack is deleting its own scratch
>    file (`export-detail.json`, `trace`). **The build passed. Nothing to do.**
> 2. **Guard fires at the START** — the log contains the error and *no* compile lines, and no
>    manifest is written. A stale `.next` is being cleared, so nothing compiled.
>
> **The guard counts deletions per turn**, and the budget is shared by everything in that turn.
> Once it has tripped, every later delete is refused too — and `rm -rf .next` is shimmed and
> blocked regardless. So:
>
> - **Never chain a delete before a build.** `rm -f old.log && npm run build` skips the build
>   entirely when the `rm` is refused, and the *previous* log is still on disk, so you inspect
>   stale output and "confirm" a failure that never happened. Use a fresh log filename per
>   attempt instead.
> - **Do not retry a blocked build in the same turn** — the counter only accumulates.
> - **To get past mode 2, move `.next` rather than deleting it.** A rename is not a delete and
>   is not intercepted:
>   ```bash
>   mkdir -p /c/Users/<user>/AppData/Local/Temp/next_stale && mv .next "$_/next"
>   ```
>   Then build. Do not leave a stale `.next*` directory inside the project — a leftover
>   `.next_old_*` was the cause of a real build failure on Day 1.

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
| The dashboard's kit/ritual type dropdown | `GET /api/festivals/choices/` publishes `FESTIVAL_CHOICES` itself (Day 8) |

**If a value is a row in the database, read it. Do not write it into a component.**

> The Day 8 case is the same trap **in reverse**, which is why the answer was not
> "derive it from the kits". Deriving the dropdown from existing kits would have
> omitted every type with no kit yet — so the first kit of a new festival type could
> never have been created, and the omission would have looked like a UI choice rather
> than a bug. An enum that the *application* owns is served from the enum; a set that
> the *database* owns is read from the database.

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

### One item editor, one domain shell

The same rule, applied to the dashboard on Day 8:

| Component | Drives |
|---|---|
| `admin-dashboard/src/components/ItemManager.js` | The item list of **both** a kit and a ritual — add a product, edit its quantity, toggle required, remove it |
| `admin-dashboard/src/components/DomainManager.js` | The list + create/edit form + delete + enable/disable shell behind `/festivals`, `/pujas`, `/vendors` **and** `/reviews` |

`DomainManager` takes a config object, and **the config must be a module-level
constant**. It is a `useCallback` dependency inside the component, so an inline object
literal is a new identity on every render and re-fetches forever.

**Do not fork either one.** A fifth collection with a list and a form is another
config, not another page. The knobs that keep it that way: omit `itemsUrl` for a
collection with no item list; give `displayName(row)` when the row's label is not
`row.name`; mark a field `createOnly` to offer it at creation and freeze it afterwards;
set `activeField` + `activeLabels` when the enable/disable boolean is not `is_active`
(reviews toggle `is_approved`, not `is_active` — patching the wrong one returns 200 and
changes nothing, which looks like it worked until you reload); and set
`canCreate: false` / `canEdit: false` for a collection that is moderated rather than
authored, so the affordance is absent instead of being rejected by the API.

### The same trap, on the storefront — and it cost a real bug

The `DomainManager` rule generalises: **any callback passed to a child that uses it in a
`useCallback` dependency must have a stable identity.** On Day 11 the product page passed
`onSummaryChange` to `ReviewsSection` as an inline arrow, and the section had it in the
dependency list of its load effect. That is an unbounded loop:

```
load() → onSummaryChange() → parent setState → parent re-render →
new arrow → new `load` identity → effect fires → load() …
```

Measured at **537 requests to the reviews endpoint in 12 seconds**, still climbing, with
the section flickering between skeletons and content. Nothing saw it — not the build, not
ESLint, not 336 unit tests, not 575 live API assertions. It surfaced only as *flakiness*
in the new browser assertion, and a request counter proved it. `storefront_check.mjs` now
pins it: two five-second windows, asserting the request count stops growing.

The fix is applied on **both** sides, and both are worth keeping: `ReviewsSection` holds
the callback in a `useRef` so it is safe by construction, and the page passes a
`useCallback` whose state update returns the previous object when the values are
unchanged. Do not "simplify" either one away.

**The same hazard was in `ToastContext`.** `success` / `error` / `info` were bare arrow
functions inside an inline object literal, so `useToast()` handed out new identities on every
render. Anything that put `error` in a `useCallback` dep would have re-created its own callback
forever. Fixed at the root with `useCallback` and a memoised value, so no consumer has to
remember. **Before adding a context, memoise what it hands out** — the cost of getting this
wrong is a request storm, not a slow render.

### Two frontend traps found on Day 12

- **`router.replace()` is a no-op when only a search-param *value* changes** on a statically
  prerendered route. Measured on `/products`: going from `/products` to `/products?q=pasni`
  worked, but replacing `?q=sindoer` with `?q=sindoor` produced **no RSC request and no URL
  change at all** — the page showed results for "sindoor" while the address bar still read
  "sindoer". The no-query case working is what made it look fine. For client-side filter
  state, use `window.history.replaceState`, which is the documented way to update search
  params from a Client Component and which the App Router keeps in step with
  `useSearchParams`.
- **A plain function named `use…` is treated as a React Hook.** `const useSuggestion = () => …`
  called from an `onClick` is a `react-hooks/rules-of-hooks` **error**, not a warning. Name
  helpers for what they do (`applySuggestion`), not for how they read.

One thing the item editor must not lose: both item list endpoints set
`pagination_class = None` and return a **bare array**. `PAGE_SIZE` is 12, Bratabandha has
14 items and Daily Puja has 21 — paginated, the editor would silently show an incomplete
kit and look correct. The tests assert a bare list specifically because a `results` dict
would still pass a `len()` check against a page. If those tests fail, fix the view.

The expanded panel row carries the global `.table-panel` class. Below 720px
`.table-wrap` pins its first column (`position: sticky`) and sets `white-space: nowrap`
on every cell, which would pin the editor and stop it wrapping. A CSS-module class
cannot win that specificity fight, so the opt-out lives in `globals.css` next to the
rules it overrides.

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
11. **Never scope a queryset with a multi-valued join if anything will group it.**
    `filter(items__product__vendor=vendor)` looks right and is wrong: an order holding two of
    that vendor's products produces **two rows**, so a later
    `values('shipping_city').annotate(Sum('total_amount'))` counts that order's total twice.
    `.distinct()` does **not** save it — Django applies DISTINCT to the grouped rows, so the
    duplication survives into the aggregate. It was invisible because a flat `.aggregate()` on
    the same queryset was correct, and only a panel that cross-checked two figures exposed it
    (measured: **2780 where the truth was 1810**). Scope with
    `Exists(Child.objects.filter(parent=OuterRef('pk'), …))` instead — no join, so `count()`,
    a flat `aggregate()` and a grouped `annotate()` are all correct by construction.
    `VendorOrderScopingTests` guards it.
12. **Every path that reserves stock must have a path that releases it.**
    `CheckoutView` decrements `product.stock` per line. Cancelling an order and deleting one
    both used to leave that decrement in place, so inventory leaked permanently — **538 units
    across 23 products** before anyone noticed, which then produced false low-stock and
    restock alerts. Cancelling now calls `release_order_stock()`; reinstating calls
    `reserve_order_stock()` and is **refused with a 400** if the stock is gone; the purge
    command releases stock for orders that still hold a reservation and skips already-cancelled
    ones (so nothing is returned twice). **`purge_verification_users` needs it too** —
    `Order.user` is `CASCADE`, so deleting a probe account silently deletes its orders as a side
    effect, and that was the *third* path with the same flaw. Any new path that creates, cancels
    or deletes an order has to answer the same question: does it reserve, and does it release?
13. **`popularity_score` is a demand signal, and it steers the AI.** It is incremented only by
    `CheckoutView`, and cancellation deliberately does **not** reverse it — a cancelled order
    still means a customer asked for something. A *fixture* order means nobody did, so
    `purge_verification_orders` reverses it for every verification order it deletes (floored at
    zero — it is a `PositiveIntegerField`). Leaving it in place had reached **591 points across
    23 products**, and the field feeds the recommender's popularity bonus, the trending list,
    the default catalogue ordering and the search tie-break — so the demo was recommending
    whatever the test suite happened to buy. Repair existing drift with
    `seed_data --reset-popularity`.
14. **A management command only exists if its app is in `INSTALLED_APPS`.**
    `core/` is the *project* package (`settings.py`, `urls.py`, `wsgi.py`) and is not installed,
    so a `seed_data.py` living there was dead code — while the docs told contributors to edit
    exactly that one. The two copies drifted, and the live one had lost its `seed_pujas` call,
    so a fresh install came up with **zero rituals**. There is now one copy, under `products/`.
    If a command seems to ignore your change, check `get_commands()`.

**`CITY_CHOICES` now lives only in `core/constants.py`** (Day 3). `Area` rows superseded it for
delivery; import the constant rather than adding another copy.

**`seed_data` exists once**, at `products/management/commands/seed_data.py`. It used to
exist twice — a second copy at `core/management/commands/` — and the guidance here said
"only `core`'s runs", **which was backwards**. `core/` is the Django *project* package
(`settings.py`, `urls.py` and `wsgi.py` live there) and is **not** in `INSTALLED_APPS`, so
Django never discovered its commands: that copy was dead code, and the file the docs told
you to edit had no effect. The two had silently diverged — the live copy never called
`seed_pujas`, so a fresh install came up with **0 rituals**, and the Puja entry point
(one of the six §1 requires) existed only on databases where somebody had run
`seed_pujas` by hand. The dead copy is deleted; `SeedDataCompletenessTests` asserts that a
plain `seed_data` produces every entry point.

> A management command only exists if its app is in `INSTALLED_APPS`. Check
> `get_commands()` when a command seems to ignore your change.

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

### Publish the resolved role, never the raw column *(added Day 9)*

`/api/auth/profile/` returns `profile.role` from `core.permissions.get_role()`, **not**
from the `UserProfile.role` column. They differ, and the difference is not cosmetic:

- `get_role()` falls back to `is_staff` for accounts created before roles existed, so a
  legacy staff user resolves to `admin` while the column still reads `customer`. Serving
  the column had the dashboard told "customer" while every request was authorised as
  "admin" — client and server disagreeing about the same user.
- The dashboard's access gate reads this value. Gating on the legacy `is_admin_user`
  boolean instead meant a **vendor could not open the dashboard at all**: the boolean is
  only ever set for `super_admin`/`admin`, so a vendor's token verified, came back
  `false`, was discarded, and the login bounced to `/login`. The VENDOR role was enforced
  correctly on every endpoint and was unreachable in the product.

**The gate is `is_staff_role(role)`, and that includes `vendor`.** If you change the
profile payload or `AdminContext`, keep those two in step — and verify it in a browser,
because no API test can see a login bounce.

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
| `promote_to_vendor(user)` | Give a `customer` account the vendor role. Returns whether it changed |
| `IsStaffRole` | Any staff role may pass |
| `IsManagerOrReadOnly` | Staff may read; only managers may write |
| `IsManager` | Managers only, **including reads**. For endpoints where reading is itself a privilege |
| `IsSuperAdmin` | Super admin only |
| `IsOwnerVendorOrManager` | Object-level: a vendor may only touch their own object |

**`IsManager` vs `IsManagerOrReadOnly`:** a vendor legitimately reads the shared
catalogue, which is why `IsManagerOrReadOnly` lets any staff role read. Use
`IsManager` for anything that enumerates *people* — currently
`/api/auth/admin/users/`, the account picker behind the vendor form. A vendor must not
be able to list the user table.

**`promote_to_vendor` is called from `AdminVendorListCreateView.perform_create`**, so
creating a shop makes its account a vendor. Two limits, both tested: it never demotes
an account that outranks `customer`, and it does **not** set `is_staff` — that would
also grant Django admin at `/admin/`, which a vendor has no business having. Deleting a
vendor does not demote either; revoking a login is an account decision, not a shop one.

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
9. **A loading flag is not a loaded flag.** `useState(false)` for `loading` means "not
   loading *yet*", which is also true before the first fetch. Any guard that reads
   `!loading && list.length === 0` therefore cannot tell "empty" from "not fetched", and
   on a fresh page load it will take the empty branch. That is not theoretical: it made a
   full page load of `/checkout` bounce to `/cart` with a full cart, and made `/cart`
   tell a customer their cart was empty. `CartContext` now exposes
   **`cartLoaded`** — true once the cart state reflects the signed-in user. Wait for that,
   not for `loading`.
10. **Redirects that depend on fetched state must not run before it arrives.** Both Day 10
    bugs were the same shape: an effect acting on data it did not have yet. If a page
    redirects on "nothing here", it must first prove the fetch happened — and a *failed*
    fetch must not look like an empty result, or a backend blip becomes a redirect.
11. **When an action empties the data a guard watches, claim the redirect first.** After a
    successful checkout the cart is empty by design, and the guard watching for an empty
    cart raced the push to the order confirmation — the order was placed and the customer
    landed on an empty cart. `/checkout` sets `placed` before calling `loadCart()`.
12. **A failed write is not a failed load.** Do not let one state variable serve both. On
    `/orders`, a rejected status PATCH set the same `error` that the *load* failure uses, so
    one refused write replaced the whole table with a block headed "Could not load orders" —
    a message that was untrue, and it destroyed the list the admin was working through.
    Keep them apart: a **load** failure may replace the screen, a **write** failure gets a
    dismissible notice (`flash(text, kind)`, self-clearing) and the data stays on screen.
    Asserted by the dashboard browser check, which forces a 400 with a route intercept.
13. **A write-triggered refresh must not blank the data.** The same screen refetched its
    list after a status change to update one "Last change" cell, and that refetch toggled
    `loading`, dropping the table to skeletons every time. Give the refresh a `silent`
    option that skips the loading state; the optimistic update already covers the row.
14. **Never write `onClick={handler}` when the handler takes an argument.** React passes the
    click event as the first parameter. `onClick={c.save}` on the settings screen handed the
    event to `save(override)`, which used it as the payload — so `JSON.stringify` ran on a
    synthetic event, threw on its circular structure, and **the request never fired**.
    Creating a category from the dashboard was simply broken, and the *other* tab worked
    because it called a local wrapper that built its payload explicitly. Write
    `onClick={() => handler()}`, and guard the handler (a React event always carries
    `nativeEvent`; a payload never does) so the mistake cannot silently recur.
    The dashboard browser check now does a create → assert → delete round trip on both tabs.

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

### Samagri search ✅ implemented *(Day 12)*

Not one of the two required AI components — it is domain logic — but it is a ranking model and
follows the same rules: deterministic, explainable, weights in one place, unit-testable.
Doc: `docs/SEARCH.md`.

- **Implementation:** `backend/products/search.py`. The view `ProductSearchView` only does
  HTTP + serialization. **Put ranking logic in `search.py`, never in the view.**
- Endpoint: `GET /api/products/search/?q=`. **Separate from `?search=` on the list
  endpoints** — the dashboard's item picker uses that one and wants a plain substring match
  over one vendor's stock. Do not merge them, and do not delete `?search=`.
- Every result carries a `match` block: `score`, `coverage`, `codes`, `reasons`. The codes must
  stay inside `REASON_CODES` and each must be traceable to a `WEIGHTS` entry — there is a test
  for exactly that, because a reason with no weight behind it is a score nobody can trace.
- **`SYNONYM_GROUPS` members are never split into their component words.** Splitting registers
  `puja` as a synonym of `thali` (from "puja plate") and `batti` as one of `dhoop` (from "dhoop
  batti"), so "puja" returns plates and "dhup" returns *Cotton Wicks*. Both were observed.
  Multi-word members match as **phrases**. There is a test class for this isolation.
- **The domain index is what makes a ritual name searchable.** No product is named after a
  ritual; the link is `PujaItem` / `KitItem`. `pasni` and `griha pravesh` returned **0**
  products before this existed.
- **Popularity is a tie-break, never part of the score.** It decides between products that
  matched equally well; it never outranks a better match.
- Changing `WEIGHTS` or `SYNONYM_GROUPS` means updating `docs/SEARCH.md` §2 — the doc quotes
  the numbers verbatim.

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
There are now **471**, covering the recommender (30), the forecaster (33), the
role/scoping system (64), order status history (23), password reset (25),
catalogue validation (17), the Puja entry point (24), add-puja-to-cart (10),
token revocation (17), ritual/kit authoring (32), vendor administration (27),
reviews (25), search (41), the wishlist (26), image upload (12), the per-area
breakdown (13), vendor order scoping (4), admin list completeness (4), cancellation/purge
stock and popularity (30) and seed completeness (13).
Live suites cover the rest:

| Suite | Assertions |
|---|---|
| `verify_day2.py` | 68 |
| `verify_day3.py` | 57 |
| `verify_day3b.py` | 41 |
| `verify_day3c.py` | 129 |
| `verify_day4.py` | 88 |
| `verify_day6.py` | 40 |
| `verify_day7.py` | 30 |
| `verify_day8.py` | 74 |
| `verify_day9.py` | 49 |
| `verify_day11.py` | 68 |
| `verify_day12.py` | 84 |
| `verify_day13.py` | 68 |
| `verify_day14.py` | 21 |
| **Total live** | **817** |
| `admin-dashboard/scripts/browser_check.mjs` | **112** (browser, not HTTP) |
| `frontend/scripts/storefront_check.mjs` | **136** (browser, not HTTP) |
| `frontend/scripts/scroll_probe.mjs` | 0 long frames of 354 (browser, perf not correctness) |

> **Discrepancy to resolve:** `browser_check.mjs` is quoted as **112** here and **119** in the
> command block in §5. One of the two is stale. Re-run it against a production build and
> correct whichever is wrong — do not "fix" the number without measuring it.

**Do not chain a sweep with `&&`.** Several of these scripts (and `curl`) exit non-zero
while succeeding — `verify_day*.py` returns its failure count, and `curl -o /dev/null`
can exit 23 on a write error after printing a healthy `200`. `cmd1 && cmd2` then silently
skips `cmd2` and the sweep reports nothing, which reads as "no failures". Use `;`.

**Start the API server with `--noreload` before a sweep.** Editing any `.py` under
`backend/` makes the autoreloader restart its child; a child that dies mid-reload leaves
the parent holding `:8000` and answering nothing at all (curl exits 56 with an empty
body). That is indistinguishable from a broken endpoint, and it made four verifiers
report "could not log in" in the same sweep.

**Run a sweep in two batches, and restart the server between them.** In a sandboxed shell
the HTTP layer saturates under a rapid burst: partway through a twelve-verifier run the
process is still listening and still logging, but requests come back `000` or `503`
intermittently and then not at all. It is an environment limit, not a Django or project
fault — the process is healthy and a restart clears it. Two batches of five and seven
complete reliably:

```bash
# batch 1
for f in verify_day2 verify_day3 verify_day3b verify_day3c verify_day4; do
  ./venv/Scripts/python.exe $f.py | tail -1
done
# restart the server, then batch 2
for f in verify_day6 verify_day7 verify_day8 verify_day9 verify_day11 verify_day12 verify_day13; do
  ./venv/Scripts/python.exe $f.py | tail -1
done
```

**An interrupted sweep leaves scratch rows behind, and they break the next run.** A wedged
server killed `verify_day3b` after it created its scratch area, and because that area was
named `Kirtipur` — a real place name with no marker — the leftover was indistinguishable
from legitimate data and made `verify_day3b` and `verify_day3c` fail on "only the three
seeded areas remain". Both verifiers now name their scratch area `ZZ E2E …` and pre-clean
that prefix. **Name scratch data so it announces itself**, and pre-clean it: a run can be
interrupted at any point.

**After any verification sweep, purge what it created** — `purge_verification_orders`,
`purge_verification_users` and `purge_verification_reviews`, all with `--dry-run`. A
verifier that leaves rows behind makes the demo order ids drift, can leave a stray login
on the system, and — for reviews — silently changes a seeded product's rating, which is
what `verify_day11.py` asserts is clean. Both browser checks now clean up after
themselves (the dashboard seeds a review through the API and deletes it; the storefront
posts one and deletes it through the UI), so a leftover review means a run was
interrupted. `verify_day12.py` writes nothing at all.

**A verifier must own every precondition it asserts.** This is the rule that both Day 11
failures turned on. `verify_day11.py` asserted "the verified-purchase badge is false before
any order" about `testuser` — and `testuser` already had an order for that product, because
the storefront browser check buys the most popular product. The feature was right; the
verifier was asserting about a history it did not control. Both checks now run as a throwaway
account the script registers itself, and in the order that makes the badge known to be false.
Ask of every assertion: *did I create the state I am about to claim?* If not, create it, or
report a labelled SKIP — never assume it.

**And a verifier must not mutate data it does not own.** The sharper edge of the same rule,
learned on Day 13: `verify_day13.py` uploaded a test image onto `kits[0]` — the **seeded**
*Bratabandha Ceremony Kit* — and never restored it, so simply running the verifier
permanently changed the demo data. Nothing failed; the damage was only visible by reading
`git status`, noticing an unexpected `media/kits/` directory, and asking the database which
files it referenced. The check now creates its own scratch kit, deletes it, and asserts that
no seeded kit points at a test upload.

> **Reading `git status` and the `media/` directory is part of a verification sweep.** A
> green run that quietly edited the fixtures is not a green run.

**And read the data before choosing a probe for it.** A Day 12 check searched for
"Retired Nonexistent Samagri" and expected nothing; "samagri" is a real word in several product
names and descriptions, so it correctly matched one. The failure was in the probe, not the
product.

**Assert the invariant, not a number that happens to hold — and self-test any helper you
parse with.** Two Day 13 checks passed for the wrong reason, and both were recorded as
evidence until they did not:

- `verify_day3c.py` asserted `count == 12` on a vendor's product list. That was the
  pagination artifact: the list was paginated at 12 and the vendor happened to own exactly 12
  products, so "12" was simultaneously the right answer and a first page indistinguishable
  from one. Unpaginating the list made the check fail while the behaviour became *more*
  correct. It now asserts ownership — every row belongs to that vendor, no unowned row leaks
  in — which holds whatever the catalogue size becomes.
- The dashboard check parsed `"Rs. 19,500"` with `replace(/[^\d.,-]/g, '')`, which keeps the
  period in `Rs.` and turns the number into `.19500` → `0.195`. It agreed with the sum on its
  first run only because every figure was then three digits, so the leading dot divided
  everything by 1000 uniformly. The app was right both times. The parser now anchors on a
  digit and **self-tests against nine known inputs** before it is trusted.

> A check that passes for the wrong reason is worse than a missing check, because it gets
> written down as proof. Before trusting a check, ask what would have to change for it to
> fail — if the answer is "almost nothing", it is not yet evidence.

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

### Verify UI changes in a browser, not just the build

**A clean build and a passing API suite cannot see a client-side render failure.**
The dashboard's `AuthGate` renders "Checking your session…" during SSR, so `curl`
gets a healthy `200` with an empty shell. The project has shipped this class of bug
twice: four `Catalog Settings` buttons that threw `ReferenceError` before their dialog
opened, and a home-page "+" that looked like add-to-cart and had no handler. Both
compiled cleanly and linted cleanly.

Day 9 added the check and it earned its keep on the first run: **a vendor could not log
into the dashboard at all**, and every API test was green. Day 10 pointed it at the
storefront and found three more — a full page load of `/checkout` bounced to `/cart`,
a successful checkout sent the customer to an empty cart instead of the confirmation,
and the "My Orders" nav link pointed at a route that did not exist. Day 11 added
assertions for the review flow and they immediately surfaced **a fetch loop on the
product page** (537 requests in 12 seconds — see §5), which had been invisible to
everything else.

**A new assertion is only trustworthy once it is run more than once.** The loop above
first appeared as an intermittent failure in *one* of three identical runs. Treat a
flaky check as a finding, not as noise to re-run past: in this case the flakiness *was*
the bug, and a check that had been accepted as "usually passes" would have shipped it.

```bash
# dashboard on :3001, storefront on :3000, API on :8000
cd admin-dashboard && NODE_PATH=/tmp/harness/node_modules node scripts/browser_check.mjs
cd frontend        && NODE_PATH=/tmp/harness/node_modules node scripts/storefront_check.mjs
```

Both drive the Edge already on the machine through `playwright-core` — no Chromium
download, and **do not add it to `package.json`**. They are dev tools, not
dependencies. `storefront_check.mjs` places one real order marked in `notes` as
`browser_check.mjs`, which `purge_verification_orders` recognises.

When you add a screen to either app, add its assertions to the matching script.

> **A harness assertion is a claim about the product — check it before trusting it.**
> Five of the first two runs' "failures" were the harness's own fault: a
> `waitForSelector` that resolved against the wrong element, an assertion that a vendor
> has no create button (it does — vendor self-service is the point), a check for
> `'Next festival'` that failed because the eyebrow is uppercased in CSS, and a
> ritual-detail check reading data off a page still showing skeletons. Assert the real
> invariant, not the one you assumed.

> **`textContent()` includes `<script>` contents — use `innerText()`.** The RSC payload
> is embedded in the HTML, so `document.body.textContent` contains data that was never
> rendered and a check can pass against a loading skeleton. `innerText` is rendered text
> only. Note the flip side: it also reflects CSS `text-transform`, so match
> case-insensitively.

> **A client-side nav updates the URL before the Server Component renders.** Waiting on
> `waitForURL` alone reads the loading fallback. Wait for the content you actually need.

> **Do not issue parallel edits to the same file.** Two edits sent in one message each
> read the file, apply, and write — so the second silently clobbers the first. This
> cost real time on Day 8: a `{hasItems && …}` guard vanished and only the browser
> caught it, because the identifier *was* defined elsewhere in the file and lint had
> nothing to complain about.

---

## 13. Security rules

- **No secrets in source.** `settings.py` currently hardcodes `SECRET_KEY` and seeds use
  `admin123`/`test1234`; move real config to environment variables when you touch settings.
- `DEBUG = True`, `ALLOWED_HOSTS = ['*']`, `CORS_ALLOW_ALL_ORIGINS = True` are **dev-only and
  must not ship**. Narrow them before any real deployment.
- ~~Remove the hardcoded credentials from `admin-dashboard/src/app/login/page.js`~~ — **done,
  verified 2026-09-23.** The form's fields are `useState('')`; this note was stale. Keep it
  that way: a pre-filled password on a login form is a credential in source.
- **`SECRET_KEY` is the JWT signing key, not just a Django setting.** Leaking it does not merely
  expose a cookie secret — anyone holding it can *mint* a valid access token for any user,
  including `admin`. Treat it as the highest-value secret in the repo. It is committed in this
  repo's history, so **rotate it before this ever leaves a private repo.**
- **`backend/db.sqlite3` is tracked**, and it holds real password hashes for `admin`,
  `testuser` and `vendor1` whose passwords are documented in this file. Fine for a private
  coursework repo; **untrack it (`git rm --cached`) if this repo is ever made public.**
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
./venv/Scripts/python.exe manage.py test          # 257 unit tests
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

**P1** wishlist · reviews/ratings · vendor self-service UI · vendor & area analytics ·
search relevance · image upload widget

**P2** live payments · notifications · advanced analytics · extra animation

**Day 5 — the festival domain, made visible (2026-09-19)** rebuilt the home page to lead with
the next festival and its required samagri, replaced three drifted product cards with one
shared `ProductCard`, and removed two more hardcoded lists. 185 unit tests + 380 live
assertions pass.

**Day 6 — the missing entry point (2026-09-19)** built `Puja` + `PujaItem`, untangling
`festival_type` (which was doing double duty for calendar festivals *and* rites of passage),
plus `/pujas`, `/pujas/<slug>` and add-essentials-to-cart. 219 unit tests + 420 live
assertions pass.

**Day 7 — token revocation (2026-09-19)** closed the one security gap the docs admitted to:
a password reset now ends existing sessions, via a `tv` version claim checked on every
request. 257 unit tests + 450 live assertions pass.

**Day 8 — domain authoring (2026-09-21)** made the puja domain editable in the dashboard.
The write endpoints for rituals, editable item rows, unpaginated item lists and the shared
`ItemManager` landed first; then `/festivals` became writable and `/pujas` was built, both
from one `DomainManager` shell. 268 unit tests + 524 live assertions pass.

**Day 9 — vendor administration, and the first browser pass (2026-09-21)** closed two gaps
that no API test could see. A vendor **could not log into the dashboard at all** — the gate
asked `is_admin_user`, a legacy boolean never set for vendors — and there was no way to
administer a vendor, so shops could only be created in Django admin. `/vendors` and the
manager-only account picker exist now, creating a shop promotes its account, and
`browser_check.mjs` verifies the dashboard in a real browser. It found the vendor bug on its
first run. 295 unit tests + 575 live assertions + 39 browser assertions pass.

**Day 10 — the storefront, driven like a customer (2026-09-21)** pointed the same kind of
check at the customer app, which had never been driven. It found three bugs that the build,
lint and 575 live API assertions all missed: **a full page load of `/checkout` bounced to
`/cart`** (refresh, bookmark, shared link — the demo's most important page was unreachable by
URL); **a successful checkout sent the customer to an empty cart** instead of the
confirmation, so the order was placed and looked like it had failed; and the **"My Orders"
nav link pointed at a route that did not exist**. All three are fixed, `/account/orders` now
exists as a real page, and `storefront_check.mjs` (44 assertions) drives browse → ritual →
product → cart → checkout → history.

**Day 11 — reviews and ratings (2026-09-21)** built the last P1 gap the brief named by
omission: `docs/DATABASE-DESIGN.md` listed a `Review` table as "not in scope; post-MVP" and
`FEATURES.md` listed "no social proof on product pages". The `Review` model, the endpoints,
the storefront section and the `/reviews` moderation screen are all in. Adding one route
**404'd the entire admin review API** — `<slug:slug>/reviews/` matched `admin/reviews/` with
`slug='admin'`, and five of six test failures were that one bug.

Then the new browser assertions for the review flow surfaced **a fetch loop on the product
page**: an inline `onSummaryChange` in a `useCallback` dependency list, at 537 requests to
the reviews endpoint in 12 seconds and still climbing. The build, ESLint, the 336 unit tests
and the live API suites all missed it; it appeared only as flakiness in a check that had been
written minutes earlier. Both causes are fixed and both are pinned by a check.

**Day 12 — the Samagri entry point (2026-09-21)** rebuilt search, the weakest of the six
discovery paths `AGENTS.md` §1 requires. It was `icontains` over name and description, which
meant `sindur`, `dhup`, `deep`, `karpoor`, `sankha`, `nariyal` and `agarbati` all returned
**zero** products; `pasni` and `griha pravesh` returned **zero** although both are seeded
rituals with complete kits, because no product is named after a ritual; and `diyo` ranked
*Cotton Wicks* above *Brass Diyo (Oil Lamp)*. All three are fixed, with every result carrying a
reason the storefront renders verbatim (`docs/SEARCH.md`). The catalogue page also stopped
showing 12 of 35 products as though that were all of them. Along the way: `ToastContext` was
handing out unstable callbacks — the same loop hazard as Day 11, fixed at the root.
**379 unit tests + 727 live assertions + 143 browser assertions pass.**

**Day 13 / 13.1 — the last P1 gaps, and inventory that was leaking (2026-09-22)** built the
wishlist, an image-upload widget and the per-area breakdown, then audited the parts nobody had
looked at. Two defects there were **invisible by construction** — both only manifest as
accumulated drift. **Cancelling an order never returned its stock**, so inventory leaked
permanently (**538 units across 23 products** before it was found, producing false restock
alerts); and `seed_data` existed twice, with the one the docs told you to edit being dead code
in a non-app package, so a fresh install seeded **0 rituals**. Every reservation now has a
release path (`release_order_stock` / `reserve_order_stock`).

**Day 14 — the five storefront routes nobody had ever loaded (2026-09-22)** closed the browser
coverage gap on `/pujas/[slug]`, `/auth/register`, `/auth/forgot-password`,
`/auth/reset-password` and `/account/orders/[id]`, and corrected two source comments that
claimed `notFound()` returns an HTTP 404 on `/pujas/[slug]`. Measured: it returns **200**,
because `src/app/pujas/loading.js` opens a Suspense boundary before the fetch resolves.
The coverage is deliberately **by URL, not by click** — Next 16 makes `params` a Promise, so a
route can render correctly on a client-side click and 404 on a direct load, and the build
catches neither.

**Day 14b — the mocked gateways now admit it (2026-09-22)** closed the last P2 honesty gap.
`CheckoutView` marked an `esewa`/`khalti` order `paid` and `confirmed` with **no gateway
involved at all**, and the dashboard, the confirmation screen and the status history all
reported it as a real payment. One module-level constant (`PAYMENT_METHODS_ARE_MOCKED`) now
drives the label everywhere; flip a value when a real integration lands and the labels vanish
on their own. `cod` is deliberately **not** labelled.

**Day 15 — a dashboard that lied to the one role nobody tested (2026-09-22)** found that
`/analytics/sales/` and `/analytics/areas/` had returned `scope: 'all' | 'vendor'` since Day 9
with **no client code reading it**. Both audiences got the same page with different numbers and
no indication which, and the Total Revenue card was captioned with the hardcoded string
`All time` — so a vendor was shown **Rs. 1,810** (their own 3 orders) under a label claiming it
was their all-time *shop* revenue, against a shop-wide **Rs. 6,760**. The API was right the
whole time. The dashboard home was also the one page the vendor browser section never visited:
it made `/reviews` its last page and never loaded `/`.

> **Two lessons worth more than the fix.**
> 1. **A route name is not evidence about what a route returns.** Day 15 opened with the
>    claim "there is no vendor analytics — `analytics/urls.py` has no vendor route", inferred
>    from listing the URLs and never calling one. The routes are global by name and scoped by
>    content. This is the same failure as a check that passes for the wrong reason: it was a
>    conclusion drawn from a proxy instead of from the thing itself.
> 2. **Ask which page has never been loaded by *which role*.** Three bugs in this project —
>    the dead "create a category" button, the `/orders` table replaced by a false error, and
>    this one — were found by coverage gaps, not by reading code. Section coverage is not role
>    coverage.

**Day 15b — two capabilities the product could not reach (2026-09-22)** asked Day 15's
question of the account endpoints: *which endpoint does no client call?* `/auth/logout-all/`
had existed since Day 7, with a docstring calling it "a real user-facing action", appearing in
`verify_day7.py` and in `docs/API-SPEC.md` — and **zero references in any UI**. Meanwhile the
only way to change a password was the forgot-password flow, which needs mailbox access and
asks you to assert you have *lost* the password. `POST /api/auth/password-change/` and an
Account Security panel on `/account` now cover both. The change **requires the current
password** — the caller is already authenticated, so without it a stolen access token alone
would lock the owner out permanently — and **revokes every token including the caller's own**,
because a change that leaves old sessions alive protects nothing already stolen.

> **The lesson, third time in one day.** Day 15: an API returning `scope` that nothing read.
> Day 15b: two security endpoints nothing called. In each case the backend was correct, tested
> and documented, and the *product* could not reach it. **Grep for every non-test reference
> before calling an endpoint "done"** — a route that exists in `urls.py` and a route a user can
> actually get to are different claims.

**Day 15c — the last endpoint nobody called, and a check that failed for a reason it never
named (2026-09-22)** finished that sweep. `/api/analytics/inventory/` was built, vendor-scoped,
routed and documented with **no test and no caller**; it now has 9 tests and a Stock Health
panel. Two things worth carrying forward from it:

- **`stock__lt=10` includes `stock=0`, so the low-stock and out-of-stock lists are nested, not
  disjoint.** Correct, but a screen rendering both would show the out-of-stock rows twice. A
  test written against the seeded catalogue could never have caught this — its minimum stock is
  **25** against a threshold of **10**, so every count is legitimately zero and the assertion
  passes whatever the code does. **A fixture must own the edge it is testing.**
- **A "regression" that was a skeleton race.** `the three seeded delivery areas are still
  listed` failed on 2 of 3 consecutive runs while all three areas sat in the database. Cause:
  deleting the scratch row sets `loading = true` and `AreasPanel` renders `.skeleton-line` divs
  *instead of* the table, and the harness waited only for the scratch **name** to vanish — which
  happens the moment the skeletons mount, before the refetch returns. Measured at that instant:
  `skeletonCount: 3, tableRowCount: 0, seesKathmandu: false`. **A loading state and an empty
  result are indistinguishable through `innerText`** — wait on the element the assertion is
  about, and assert the row count so the two stay separable. One of the three runs also printed
  no summary at all, because an unguarded `waitForSelector` throws out of `main()`.

> **Corollary, and the sharpest one yet: do not keep an explanation that fits.** I had seen this
> same failure earlier and attributed it to two harnesses running concurrently. It reproduces
> with one process. **A convenient explanation for a passing-then-failing check is a hypothesis,
> not a finding** — measure the DOM at the failure instant before you believe it.

**The shopping flow already works.** Do not rebuild it. Fix, extend, and polish.

---

## 15. Do not unnecessarily change

These are working and load-bearing. Improve around them; do not rewrite them.

- **The database schema.** 35 products, 10 categories, 7 kits, 67 kit items, 8 rituals,
  88 ritual items, 10 festivals and 8 orders are already seeded and coherent. Additive
  changes only.
- **The six public endpoint URLs** in `core/urls.py`. Both frontends depend on them.
- **`globals.css` and the CSS-module approach.** The token system is good. Extend it.
- **The split serializer pattern** (public vs admin) in `products`/`festivals`.
- **The `accounts` / `products` / `festivals` / `orders` / `analytics` app split.**
- **`analytics` having no models** — plain aggregation is the right design here.
- **`OrderItem`'s `product_name` + `price` snapshot.** Orders must survive price changes.
- **`KitItem.is_required`** — it is the required-samagri mechanism.
- **The item list endpoints' `pagination_class = None` and `RetrieveUpdateDestroyAPIView`
  detail views** (`AdminKitItem*`, `AdminPujaItem*`). Deliberate; see §5.
- **`AdminUserListView`'s `IsManager` and `pagination_class = None`.** It feeds a
  `<select>`, and read access is deliberately narrower than the rest of the admin API.
- **The dashboard's role gate** (`AdminContext` + the resolved role in the profile
  payload). This is what lets a vendor in; see §7.
- **The JWT + 401-refresh logic in `frontend/src/lib/api.js`.**
- **`CartContext`'s `cartLoaded` flag, and the redirect guards in `/checkout` and
  `/cart` that read it.** Removing it re-introduces the Day 10 bugs; see §9 rules 9–11.
- **The React Context providers** (`Auth`, `Cart`, `Toast`) and the `layout.js` composition.
  Note that `ToastContext` memoises its callbacks and its value — that is load-bearing, not
  tidiness; see §5.
- **`?search=` on the product list endpoints.** The dashboard's item picker depends on it and
  wants a plain substring match over one vendor's stock. `/products/search/` is a different
  job and does not replace it.
- **`products/search.py`'s `SYNONYM_GROUPS` isolation and the `WEIGHTS` table.** Extending
  them is expected; splitting group members into words is a bug, and moving a weight means
  updating `docs/SEARCH.md` §2.
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
