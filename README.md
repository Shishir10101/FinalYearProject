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
| Auth | `auth/register/` · `auth/login/` · `auth/token/refresh/` · `auth/profile/` · `auth/password-reset/` · `auth/password-reset/confirm/` |
| Products | `products/` · `products/featured/` · `products/categories/` · `products/<slug>/` |
| Festivals | `festivals/kits/` · `festivals/kits/<id>/` · `festivals/upcoming/` · `festivals/recommendations/` |
| Cart | `orders/cart/` · `orders/cart/add/` · `orders/cart/update/<id>/` · `orders/cart/remove/<id>/` · `orders/cart/add-kit/<kit_id>/` |
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
(real token flow: single-use, expires in 24 h, no account enumeration)

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
cd backend         && venv/Scripts/python.exe manage.py test    # 185 tests
```

Live end-to-end checks (backend must be running on :8000):

```bash
cd backend && venv/Scripts/python.exe verify_day2.py     #  68 assertions
cd backend && venv/Scripts/python.exe verify_day3.py     #  55 assertions
cd backend && venv/Scripts/python.exe verify_day3b.py    #  41 assertions
cd backend && venv/Scripts/python.exe verify_day3c.py    # 128 assertions (full purchase path)
cd backend && venv/Scripts/python.exe verify_day4.py     #  88 assertions (history, reset, validation)
cd backend && venv/Scripts/python.exe manage.py purge_verification_orders   # clean up after
cd backend && venv/Scripts/python.exe manage.py purge_verification_users
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

**Last verified:** 2026-09-19 — **185 unit tests + 380 live E2E assertions** passing, both
frontends building clean (13/13 customer routes, 10/10 admin routes), authorization tests
correct, and the database back to its seeded state (8 orders · 35 products · 10 categories ·
3 areas · 1 vendor · 8 status events · 0 scratch rows) after purging.

The home page leads with the **festival calendar** — the next festival, its countdown, its
kit (or a plain statement that there is no kit yet) and the required samagri — rather than a
generic product grid.

