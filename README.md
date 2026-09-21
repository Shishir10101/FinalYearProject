# Puja Samagri Store Nepal

Online Puja Samagri e-commerce platform for **Kathmandu Valley**
(Kathmandu · Lalitpur · Bhaktapur).

Discovery is built around the **festival / puja / samagri** domain — not generic retail.

```
Product · Category · Festival · Puja · Samagri · Ready-made Kit
```

---

## Quick start

Three processes. Open three terminals.

**1 — Backend** (Django + DRF, SQLite) → http://127.0.0.1:8000

```bash
cd backend
venv/Scripts/python.exe manage.py migrate
venv/Scripts/python.exe manage.py seed_data              # only if the DB is empty
venv/Scripts/python.exe manage.py refresh_festivals      # keep the festival calendar in the future
venv/Scripts/python.exe manage.py generate_synthetic_sales   # demand-forecast dataset (SYNTHETIC)
venv/Scripts/python.exe manage.py runserver 8000
```

> `refresh_festivals` is **not optional** for a good demo. It re-anchors the festival
> calendar to today. Run it if recommendations look like a plain best-seller list, or if
> the home page says "No upcoming festivals scheduled".
>
> `generate_synthetic_sales` builds the **synthetic** dataset the demand forecaster
> trains on. See `docs/AI-PREDICTION.md` — this data is fabricated and labelled as such
> everywhere it appears.

**2 — Customer storefront** (Next.js) → http://localhost:3000

```bash
cd frontend
npm install
npm run dev
```

**3 — Admin dashboard** (Next.js) → http://localhost:3001

```bash
cd admin-dashboard
npm install
npm run dev -- -p 3001
```

### Demo credentials

| Role | Username | Password |
|---|---|---|
| Super Admin | `admin` | `admin123` |
| Customer | `testuser` | `test1234` |

Development credentials only. See `AGENTS.md` §Security before any deployment.

---

## Repository layout

```
project_7/
├── backend/            Django 4.2 + DRF · SQLite · :8000
├── frontend/           Next.js 16 customer storefront · :3000
├── admin-dashboard/    Next.js 16 admin panel · :3001
├── docs/               Development references
└── AGENTS.md           Rules for coding sessions — read before changing anything
```

`backend/`, `frontend/` and `admin-dashboard/` are **separate git repositories**.
The project root is not a repo.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Django 4.2 · Django REST Framework |
| Auth | JWT (djangorestframework-simplejwt) |
| Database | SQLite (`backend/db.sqlite3`) |
| Frontend | Next.js 16 App Router · React 19 · JavaScript |
| Styling | CSS Modules + design tokens in `globals.css` |

---

## API surface

Base: `http://127.0.0.1:8000/api`

| Group | Endpoints |
|---|---|
| Auth | `auth/register/` · `auth/login/` · `auth/token/refresh/` · `auth/profile/` · `auth/password-reset/` · `auth/password-reset/confirm/` · `auth/logout-all/` |
| Products | `products/` · `products/featured/` · `products/categories/` · `products/<slug>/` |
| Festivals | `festivals/kits/` · `festivals/kits/<id>/` · `festivals/upcoming/` · `festivals/recommendations/` |
| Rituals | `festivals/pujas/` · `festivals/pujas/<slug>/` |
| Cart | `orders/cart/` · `orders/cart/add/` · `orders/cart/update/<id>/` · `orders/cart/remove/<id>/` · `orders/cart/add-kit/<kit_id>/` · `orders/cart/add-puja/<puja_id>/` |
| Orders | `orders/config/` · `orders/checkout/` · `orders/` · `orders/<id>/` |
| Admin | `products/admin/*` · `orders/admin/*` · `festivals/admin/*` · `analytics/*` |

### AI endpoints

| Endpoint | Auth | Notes |
|---|---|---|
| `GET festivals/recommendations/?limit=` | public | Ranked, explainable. Each product carries `recommendation.reasons[]`. Personalises when authenticated. |
| `GET analytics/demand-forecast/?horizon=&limit=&product=` | admin | Per-product forecast. Response carries `data_source: "synthetic"` and a `provenance_note`. |
| `GET analytics/predictions/` | admin | Alerts incl. forecast-driven `forecast_restock`. |

Django admin: http://127.0.0.1:8000/admin/

---

## Roles

```
SUPER ADMIN  →  manages administrators, areas, system
     ↓
   ADMIN     →  vendors, products, orders; scoped to an assigned area
     ↓
   VENDOR    →  own products, inventory, orders
              
   CUSTOMER  →  separate customer role
```

> **Status:** today only Super Admin (any `is_staff` user) and Customer are enforced.
> The `Vendor` role and the Super-Admin/Admin split are not yet implemented, and
> `UserProfile.is_admin_user` is not read by any permission check.
> See `docs/CURRENT-STATE.md` §Broken B5.

---

## Documentation

| File | Contents |
|---|---|
| `AGENTS.md` | Rules for coding sessions — conventions, authorization, UX, security |
| `docs/CURRENT-STATE.md` | **Start here.** What works, what is broken, what is missing, priorities |
| `docs/DEVELOPMENT-ROADMAP.md` | The 2–3 day execution plan, phase by phase |
| `docs/FEATURES.md` | Feature inventory and status |
| `docs/DATABASE-DESIGN.md` | Schema and relationships |
| `docs/API-SPEC.md` | Endpoint reference |
| `docs/AI-RECOMMENDATION.md` | Recommendation approach and scoring |
| `docs/AI-PREDICTION.md` | Demand prediction approach, metrics, limitations |
| `docs/UI-UX-SPEC.md` | Design system and UI rules |

## Features

**Shopping** — browse · search · categories · product details · cart · checkout ·
order history · **order status timeline with real per-step timestamps** ·
ready-made festival kits · add-whole-kit-to-cart

**Account** — register · login · JWT refresh · profile edit · **password reset**
(real token flow: single-use, expires in 24 h, no account enumeration) ·
**sign out everywhere**, and a reset that actually ends existing sessions

**Festivals** — festivals · pujas · required samagri · product relationships · curated kits

**Vendor** — product management · inventory · orders · scoped to their own rows

**Admin** — products · orders · festival kits · dashboard · **demand forecast** ·
catalog settings (categories, delivery areas) · per-field validation on every form

**AI**
- **Samagri recommendation** — ranked and explainable. Seven weighted signals; every
  product carries a human-readable reason. Personalises from order history when available.
  → `docs/AI-RECOMMENDATION.md`
- **Product demand prediction** — a real seasonal-trend model with an honest held-out
  accuracy figure. **⚠️ Fitted on labelled synthetic data** — see the doc before quoting
  any number. → `docs/AI-PREDICTION.md`

---

## Build verification

```bash
cd frontend        && npm run build      # must pass
cd admin-dashboard && npm run build      # must pass
cd backend         && venv/Scripts/python.exe manage.py check
cd backend         && venv/Scripts/python.exe manage.py test    # 379 tests
```

Live end-to-end checks (backend must be running on :8000):

```bash
cd backend && venv/Scripts/python.exe verify_day2.py     #  68 assertions
cd backend && venv/Scripts/python.exe verify_day3.py     #  55 assertions
cd backend && venv/Scripts/python.exe verify_day3b.py    #  41 assertions
cd backend && venv/Scripts/python.exe verify_day3c.py    # 128 assertions (full purchase path)
cd backend && venv/Scripts/python.exe verify_day4.py     #  88 assertions (history, reset, validation)
cd backend && venv/Scripts/python.exe verify_day6.py     #  40 assertions (the ritual entry point)
cd backend && venv/Scripts/python.exe verify_day7.py     #  30 assertions (token revocation)
cd backend && venv/Scripts/python.exe verify_day8.py     #  74 assertions (kit & ritual authoring)
cd backend && venv/Scripts/python.exe verify_day9.py     #  49 assertions (vendor administration)
cd backend && venv/Scripts/python.exe verify_day11.py    #  68 assertions (reviews & moderation)
cd backend && venv/Scripts/python.exe verify_day12.py    #  84 assertions (search & ranking)
cd backend && venv/Scripts/python.exe manage.py purge_verification_orders   # clean up after
cd backend && venv/Scripts/python.exe manage.py purge_verification_users
cd backend && venv/Scripts/python.exe manage.py purge_verification_reviews
```

Run the purge commands afterwards: the verifiers exercise the real checkout and
registration APIs, so they create real orders and a throwaway account. The commands
remove only rows carrying a verifier marker and never touch the seeded demo data.
`--dry-run` lists what would be removed.

Catch undefined-identifier bugs before they reach a click handler — the project's
ESLint config does not enable `no-undef`, so `next lint` stays silent:

```bash
cd frontend        && npx eslint --rule '{"no-undef":"error"}' src/
cd admin-dashboard && npx eslint --rule '{"no-undef":"error"}' src/
```

No feature is complete until its build is clean and the flow has been exercised end to end.

**Last verified:** 2026-09-21 — **379 unit tests + 727 live E2E assertions + 143 browser
assertions** passing, both frontends building clean (14/14 customer pages, 13/13 admin
pages), authorization tests correct, and the database back to its seeded state (8 orders ·
35 products · 10 categories · 3 areas · 1 vendor · 7 kits · 8 rituals · 8 status events ·
0 reviews · 0 scratch rows) after purging.

Discovery works through the six paths the brief requires — **Product · Category · Festival ·
Puja · Samagri · Ready-made Kit** — and the last of those is a real search rather than a
substring box: it resolves alternative spellings of a Nepali term (`sindur` finds *Sindoor
Powder*), reaches the samagri behind a ritual or festival name (`pasni` returns the nine items
of a ritual none of them is named after), ranks by how well a product matches rather than by
popularity, and tells the shopper why each result is there. See `docs/SEARCH.md`.

The home page leads with the **festival calendar** — the next festival, its countdown, its
kit (or a plain statement that there is no kit yet) and the required samagri — rather than a
generic product grid.

The admin dashboard can **author the whole domain**: products, categories, delivery areas,
festival kits and rituals (including the samagri list behind each), and vendors — all from
one shared editor. All three staff roles can log in; a vendor sees only its own catalogue.

Two browser checks verify the apps in a real browser — `admin-dashboard/scripts/browser_check.mjs`
and `frontend/scripts/storefront_check.mjs` — because a clean build and a green API suite
cannot see a client-side render failure. Between them they have found five real bugs:
**a vendor could not log into the dashboard at all**, **a full page load of `/checkout`
bounced to `/cart`**, **a successful checkout sent the customer to an empty cart instead of
the confirmation**, **the "My Orders" nav link pointed at a route that did not exist**, and
**the product page refetched its reviews forever** — 537 requests in 12 seconds, invisible to
the build, to ESLint, to 379 unit tests and to every live API assertion.

Run them against a **production build**, and start the two frontends sequentially with an
explicit port: under `next dev` the HMR websocket fails in a sandboxed shell and the client
never hydrates, and two `next dev` servers started at once race for `:3000` and silently swap
ports.

