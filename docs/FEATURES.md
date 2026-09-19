# Features

What exists, what works, and what is honestly not there yet.
Every ✅ below was verified against the running system, not inferred from code.

**Legend:** ✅ working · ⚠️ works with a caveat · ❌ not built

---

## 1. The domain: Puja Samagri, not a generic marketplace

The differentiator is the festival/Puja structure layered **on top of** ordinary
e-commerce. Three first-class concepts exist that a generic shop would not have:

| Concept | Model | Why it matters |
|---|---|---|
| **Festival calendar** | `UpcomingFestival` | Drives urgency, recommendations, and demand forecasting |
| **Ready-made kit** | `FestivalKit` → `KitItem` | One-click "buy everything for Dashain" |
| **Required vs optional samagri** | `KitItem.is_required` | Distinguishes "you must have this" from "nice to have" |
| **Delivery areas** | `Area` (Kathmandu / Lalitpur / Bhaktapur) | Valley-specific logistics, per-area fees |

---

## 2. Customer storefront (`frontend`, :3000)

### 2.1 Browsing and discovery

| Feature | Status | Notes |
|---|---|---|
| Home page | ✅ | **Festival-first**: next-festival spotlight with countdown, required samagri, recommendations, then the calendar |
| Product catalogue | ✅ | Paginated, 12/page |
| Category browse | ✅ | 10 seeded categories |
| Product detail | ✅ | By slug; shows category, vendor, unit, stock state |
| Search | ✅ | By name and description (DRF `SearchFilter`) |
| Sort | ✅ | Price / stock / popularity |
| Festival browse | ✅ | 7 kits; the type filter is derived from the kits, not hardcoded |
| Festival calendar | ✅ | Soonest-first, `?limit=` up to 50 |
| Area-aware storefront | ✅ | Areas served from `/products/areas/`, not hardcoded |
| **Shared product card** | ✅ | One `ProductCard` for home / catalogue / recommendations |

### 2.2 Cart and checkout — the required E2E path

```
HOME → CATEGORY/FESTIVAL → PRODUCT LIST → DETAILS → ADD TO CART
     → CART → CHECKOUT → ORDER CONFIRMATION → ORDER HISTORY
```

| Step | Status | Notes |
|---|---|---|
| Add to cart | ✅ | Rejects quantity > stock |
| Add whole kit | ✅ | `POST /orders/cart/add-kit/<id>/` |
| Update / remove line | ✅ | |
| Cart totals | ✅ | `subtotal + delivery_fee`, fee served from the API |
| Checkout | ✅ | `transaction.atomic`; re-checks stock; decrements; clears cart |
| Over-stock at checkout | ✅ | 400 with the product name and remaining count |
| Empty cart | ✅ | 400, and the page redirects to `/cart` |
| Area selection | ✅ | **Fetched from the DB**; per-area fee override honoured |
| Order confirmation | ✅ | Redirects to the order detail page |
| Order history | ✅ | `/account`, paginated, 5 shown |
| **Order status timeline** | ✅ | 5-step tracker + a distinct cancelled state |
| **Real status timestamps** | ✅ | Each step shows *when* it happened, from `OrderStatusEvent` |
| **Cancellation time** | ✅ | The cancelled state carries its own timestamp |

### 2.3 Account

| Feature | Status |
|---|---|
| Register / login / logout | ✅ |
| JWT refresh | ✅ (access 1 day, refresh 7 days, rotation on) |
| Profile view + edit | ✅ |
| Area dropdown from the DB | ✅ |
| **Password reset** | ✅ Real token flow — works once, expires in 24 h, no account enumeration |
| Wishlist / reviews | ❌ Not built (P1) |

### 2.4 Recommendations

| Feature | Status |
|---|---|
| Ranked recommendation page | ✅ `/recommendations` |
| Every item carries an explanation | ✅ 8/8 verified rendering a reason |
| Festival urgency badge | ✅ *Required for Dashain in 18 days* |
| Personalisation from order history | ✅ |
| Stable ordering across requests | ✅ Deterministic sort key |

See `docs/AI-RECOMMENDATION.md`.

---

## 3. Admin dashboard (`admin-dashboard`, :3001)

### 3.1 Access control

| Feature | Status | Notes |
|---|---|---|
| Login gate | ✅ | Verifies the token against `/auth/profile/`, not just its presence |
| Role-aware navigation | ✅ | Manager-only items hidden from vendors |
| Role badge in the sidebar | ✅ | Super Admin / Administrator / Vendor |
| Client-side guard | ⚠️ | A **UX guard only** — every action is enforced server-side |

### 3.2 Management screens

| Screen | Status | Capabilities |
|---|---|---|
| Dashboard | ✅ | KPIs, priority alerts, revenue chart |
| Products | ✅ | **Create · Edit · Delete · Enable/Disable**, search, stock badges |
| Orders | ✅ | List, filter, change status; vendor-scoped |
| Festival Kits | ✅ | List; write endpoints exist, kit-editor UI not rebuilt |
| Demand Forecast | ✅ | Restock table, sparklines, MAPE, per-row "Why?" |
| **Catalog Settings** | ✅ | Categories CRUD + Delivery Areas CRUD with fee overrides |
| Vendor management screen | ❌ | API complete and scoped; no dedicated UI (P1) |

### 3.3 Four-state handling

Every async surface shows **loading · success · empty · error**:

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Products table | skeleton rows | "No products… use New Product" | message + Try again |
| Categories / Areas | skeleton rows | explanatory | message + Try again |
| Orders | skeleton | explanatory | message + Try again |
| Forecast | skeleton | "run generate_synthetic_sales" | message + Try again |
| Customer order detail | skeletons | n/a | distinguishes *not found* from *load failed* |
| Customer order list | skeleton cards | "No orders yet" + CTA | message + Try again |

**Known gap:** `admin-dashboard` modals show per-field validation, driven by the
DRF error body, with a safety net that renders any field the server rejects that
has no input on screen. A single general banner is used only when the error is not
attributable to a field.

---

## 4. AI / ML features

Two **separate** features, as required. Neither is fake — no random-product buttons.

### 4.1 Recommendation ✅

A weighted, explainable ranker over 7 signals. Every recommendation carries the
reason it was made, and the UI renders that reason rather than inventing one.

**Signals:** festival requirement (required/optional) · staple samagri · user
category affinity · kit affinity · repeat purchase · catalogue popularity.

Evaluated deterministically; 23 unit tests assert *ordering and explanation*, not
just response shape. Documented in `docs/AI-RECOMMENDATION.md`.

### 4.2 Demand prediction ✅ — with labelled synthetic data

A dependency-free multiplicative decomposition:
`level × weekday factor × festival ramp × damped trend`.

| Metric | Value |
|---|---|
| Holdout MAPE | **26.20%** |
| MAE | 0.810 (vs naive 0.936 → **+13.5%**) |
| Recovered Saturday spike | truth 1.30 → learned 1.191 |
| Recovered Tuesday trough | truth 0.90 → learned 0.842 |

> ⚠️ **The training data is SYNTHETIC.** 13,600 generated rows, all flagged
> `is_synthetic=True`. Every API response carries `data_source: "synthetic"` and a
> `provenance_note`. The table is deliberately kept separate from `orders` so
> fabricated rows can never be mistaken for real sales.

Documented honestly in `docs/AI-PREDICTION.md`, including the caveat that 24 of 35
restock flags are a synthetic-calibration artifact rather than a genuine finding.

---

## 5. Roles and authorization

| Role | Scope |
|---|---|
| **Super Admin** | Everything |
| **Admin** | Catalogue, kits, orders, vendors, areas |
| **Vendor** | Only their own products, and orders containing them |
| **Customer** | Own cart, own orders |

| Capability | customer | vendor | admin | super |
|---|---|---|---|---|
| Browse catalogue | ✅ | ✅ | ✅ | ✅ |
| Own cart / orders | ✅ | ✅ | ✅ | ✅ |
| Analytics | ❌ 403 | ✅ *12 products* | ✅ *35* | ✅ |
| Manage products | ❌ 403 | ✅ *own only* | ✅ | ✅ |
| Manage orders | ❌ 403 | ✅ *own only* | ✅ | ✅ |
| Categories (read / write) | ❌ / ❌ | ✅ / ❌ | ✅ / ✅ | ✅ |
| Areas, vendors (write) | ❌ | ❌ | ✅ | ✅ |
| Assign a product to any vendor | ❌ | ❌ | ✅ | ✅ |

Enforced in `get_queryset()`, not the UI. A vendor requesting another vendor's
object gets **404**, not 403 — no existence leak.

**Verified:** 47 unit tests + 55 live assertions (`verify_day3.py`).

---

## 6. What is NOT built

Honest list of gaps, so nothing here is mistaken for finished work.

| Feature | Status | Impact |
|---|---|---|
| Payment gateway | ❌ | `esewa`/`khalti` are **mocked** — they just mark the order paid |
| Reviews / ratings | ❌ | No social proof on product pages |
| Wishlist | ❌ | — |
| Vendor self-service UI | ❌ | Vendor accounts work via the API; no dedicated screen |
| Kit editor UI | ❌ | Endpoints work; no drag-and-drop kit builder |
| Email / SMS notifications | ❌ | Reset mail sends (console backend in dev); no order notifications |
| Real sales data | ❌ | Forecast trains on synthetic data; order volume is too low to train on |
| Search relevance tuning | ⚠️ | `icontains` matching; no fuzzy or typo tolerance |
| Image upload UI | ⚠️ | The field is open in the admin serializer; no upload widget |
| JWT revocation on password reset | ⚠️ | Access tokens are stateless and last a day, so a reset does not kill existing sessions |
| Order history for pre-Day-4 orders | ⚠️ | Backfilled with a single event, so their earlier steps show "not recorded" rather than an invented time |
| Festival-specific kits | ⚠️ | 3 of the 6 soonest festivals have no kit (Ganesh Chaturthi, Haritalika Teej, Indra Jatra). The home page says so plainly and routes to the recommender |

### Fixed on Day 5 (2026-09-19)

| Issue | Detail |
|---|---|
| **Home page led with a generic product grid** | The project's differentiator was invisible on the first screen. Now leads with the next festival, its countdown, its required samagri and the recommendations. |
| **Three product cards had drifted apart** | Home, catalogue and recommendations each had their own markup. The home version omitted the unit and its "+" button had **no handler** — it looked like add-to-cart and did nothing. One shared `ProductCard` now. |
| **Festival type filter was hardcoded** | Seven types listed in the page. Same trap as the old hardcoded `CITY_CHOICES`: a kit for an unlisted type would exist but be unreachable. Now derived from the kits. |
| **5 of 10 festivals were unreachable** | `/festivals/upcoming/` was hardcoded to `[:5]`. Now `?limit=` (default 5, max 50). |

### Fixed on Day 4 (2026-09-19)

| Issue | Detail |
|---|---|
| **Order timeline could not say *when*** | Derived from `Order.status`, so every completed step was permanently undated. Now driven by an append-only `OrderStatusEvent` table. |
| **Password reset did not exist** | Now a real `PasswordResetTokenGenerator` flow, throttled, single-use, with no account enumeration. |
| **`Catalog Settings` threw on every button** | Four undefined `setFieldError` calls — every New/Edit button raised `ReferenceError` before its dialog opened. |
| **Per-field validation was dead code** | The products modal always set a general banner, so the per-field spans were unreachable. |
| **Negative price accepted** | Would subtract from the cart total. Now rejected. |
| **Negative delivery fee accepted** | The store would have paid the customer to deliver. Now rejected. |
| **Duplicate category names accepted silently** | Filed as `puja-oils-ghee-1`, splitting one category into two. Now rejected. |
| **No rollback path existed** | `backend/` and the project root were not git repositories; the Day 1–3 work was uncommitted everywhere. |

### Fixed in the final pass (were broken, now working)

| Issue | Detail |
|---|---|
| **Product detail page 404'd** | `ProductDetailView` existed but was **never routed**. Every "View details" click failed. Now `products/urls.py` routes `<slug:slug>/` last among the public patterns. |
| **Duplicate names caused HTTP 500** | `Area.save()` and `Category.save()` did not uniquify slugs, so repeating a name raised an unhandled `IntegrityError`. Both suffix now. |
| **Seeded vendor had a blank slug** | Historical models inside migrations have no overridden `save()`, so the row shipped with `slug=''`. Fixed in the model and the migration. |
| Admin tables on narrow screens | Every admin `<table>` now scrolls horizontally with a pinned first column. |
| Admin sidebar on phones | The fixed 250px sidebar left 150px of content on a 400px screen. It is now an off-canvas drawer below 880px. |

---

## 7. Demo script

The path that works end to end today.

```
1.  Start backend :8000, frontend :3000, admin :3001
2.  Home → festival calendar shows real upcoming dates
3.  Click Dashain kit → see required samagri
4.  Browse a category → filter by price
5.  Open a product → add to cart
6.  Cart → totals include delivery fee, served from the API
7.  Checkout → pick an area (fetched from the DB) → place order
8.  Order confirmation → **status timeline** shows step 1 active
9.  /account → order appears in history with live status
10. Open the order → **each completed step shows the time it happened**
11. /recommendations → every card explains *why* it was recommended
12. Log out → "Forgot password?" → enter `test@example.com`
13. The dev panel shows the reset link (no mailbox configured) → open it
14. Choose a new password → sign in with it
15. admin :3001 login as admin/admin123
16. Products → create a product, edit its price, toggle it inactive
17. Products → try price `-5` → the field itself shows the error
18. Catalog Settings → add a delivery area with a fee override
19. Back to customer checkout → the new area appears with its fee
20. Log out, log in as vendor1/vendor1234
21. Dashboard shows 12 products, not 35 — vendor scoping is visible
22. Products → only their own rows; no "Catalog Settings" in the sidebar
23. Orders → change a status; the "Last change" column updates
24. Demand Forecast → synthetic banner visible, restock table, MAPE per product
```

**Demo credentials:** `admin/admin123` (super admin) · `vendor1/vendor1234` (vendor)
· `testuser/test1234` (customer)

> Note: the reset in step 13 changes a demo password. Use the customer account, and
> either set it back to `test1234` afterwards or accept the new one for the rest of
> the session. `PASSWORD_RESET_EXPOSE_LINK` must be `False` in any real deployment.
