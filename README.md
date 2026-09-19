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
| Auth | `auth/register/` · `auth/login/` · `auth/token/refresh/` · `auth/profile/` |
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
order history · ready-made festival kits · add-whole-kit-to-cart

**Festivals** — festivals · pujas · required samagri · product relationships · curated kits

**Vendor** — product management · inventory · orders _(role not yet enforced — Day 3)_

**Admin** — products · orders · festival kits · dashboard · **demand forecast**

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
cd backend         && venv/Scripts/python.exe manage.py test    # 113 tests
```

Live end-to-end checks (backend must be running on :8000):

```bash
cd backend && venv/Scripts/python.exe verify_day2.py     #  68 assertions
cd backend && venv/Scripts/python.exe verify_day3.py     #  55 assertions
cd backend && venv/Scripts/python.exe verify_day3b.py    #  41 assertions
cd backend && venv/Scripts/python.exe verify_day3c.py    # 128 assertions (full purchase path)
cd backend && venv/Scripts/python.exe manage.py purge_verification_orders   # clean up after
```

Run `purge_verification_orders` afterwards: the verifiers exercise the real checkout API,
so they create real orders. The command removes only rows carrying a verifier marker and
never touches the seeded demo orders. `--dry-run` lists what it would remove.

No feature is complete until its build is clean and the flow has been exercised end to end.

**Last verified:** 2026-09-18 — **113 unit tests + 292 live E2E assertions** passing, both
frontends building clean, 9/9 API routes, 10/10 customer routes and 7/7 admin routes
returning 200, authorization tests correct, and the database back to its seeded state
(8 orders · 35 products · 3 areas · 1 vendor · 0 scratch rows) after purging.

