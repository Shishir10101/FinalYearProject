# Features

What exists, what works, and what is honestly not there yet.
Every ✅ below was verified against the running system, not inferred from code.

**Legend:** ✅ working · ⚠️ works with a caveat · ❌ not built

---

## 1. The domain: Puja Samagri, not a generic marketplace

The differentiator is the festival/Puja structure layered **on top of** ordinary
e-commerce. Five first-class concepts exist that a generic shop would not have:

| Concept | Model | Why it matters |
|---|---|---|
| **Festival calendar** | `UpcomingFestival` | Drives urgency, recommendations, and demand forecasting |
| **Ritual (Puja)** | `Puja` → `PujaItem` | Browse by ceremony — the fourth discovery entry point |
| **Ready-made kit** | `FestivalKit` → `KitItem` | One-click "buy everything for Dashain" |
| **Required vs optional samagri** | `is_required` on both `KitItem` and `PujaItem` | Distinguishes "you must have this" from "nice to have" |
| **Delivery areas** | `Area` (Kathmandu / Lalitpur / Bhaktapur) | Valley-specific logistics, per-area fees |

### The six discovery entry points

`AGENTS.md` §1 requires discovery through six paths, not just a product grid:

| Entry point | Where it lives |
|---|---|
| Product | `/products` · `/products/<slug>` |
| Category | `/products` sidebar |
| Festival | `/festivals` · the home-page calendar |
| **Puja (ritual)** | **`/pujas` · `/pujas/<slug>`** |
| Samagri | **`/products?q=`** — domain-aware search (`docs/SEARCH.md`) + the recommender's `staple_samagri` signal |
| Ready-made Kit | `/festivals` kit grid · add-whole-kit |

**Puja was missing until Day 6** — no model, endpoint or page. The `festival_type`
enum had been doing double duty: it held `dashain`/`tihar`/`shivaratri`, which are
calendar festivals, *and* `bratabandha`/`pasni`/`griha_pravesh`/`shraddha`, which
are rites of passage. Two of its own labels even end in "Puja".

A ritual and a kit answer different questions — *"what does this ceremony need?"*
versus *"what can I buy in one click?"* — and a ritual can exist before anyone
assembles a kit for it. **3 of the 8 seeded rituals have no kit**, so that is the
normal case rather than an edge one.

---

## 2. Customer storefront (`frontend`, :3000)

### 2.1 Browsing and discovery

| Feature | Status | Notes |
|---|---|---|
| Home page | ✅ | **Festival-first**: next-festival spotlight with countdown, required samagri, recommendations, then the calendar |
| Product catalogue | ✅ | Paginated, 12/page |
| Category browse | ✅ | 10 seeded categories |
| Product detail | ✅ | By slug; shows category, vendor, unit, stock state |
| **Ratings and reviews** | ✅ | Average + 5-to-1 distribution, the review list, and write/edit/delete for your own. See §2.5 |
| **Search** | ✅ | **Rebuilt Day 12** — relevance-ranked, transliteration-aware, reaches the samagri behind a ritual or festival name. See §2.6 |
| Sort | ✅ | Price / stock / popularity |
| Festival browse | ✅ | 7 kits; the type filter is derived from the kits, not hardcoded |
| Festival calendar | ✅ | Soonest-first, `?limit=` up to 50 |
| **Ritual browse** | ✅ | `/pujas` — 8 rituals, essentials marked, no kit required |
| **Ritual detail** | ✅ | `/pujas/<slug>` — essential vs optional samagri, add-essentials-to-cart |
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
| **Sign out everywhere** | ✅ `POST /auth/logout-all/` revokes every token for the account |
| **Token revocation** | ✅ A reset ends existing sessions, including unexpired access tokens |
| **Full order history** | ✅ `/account/orders` — every order, paginated by walking `?page=` |
| **Reviews and ratings** | ✅ **Built on Day 11** — write, edit and delete your own from the product page |
| Wishlist | ❌ Not built (P1) |

> `/account` shows the five most recent orders under "Recent Orders". The **My Orders**
> item in the account dropdown used to link to `/account/orders`, which did not exist —
> it landed on the 404. Found by the storefront browser check; see §Fixed on Day 10.

### 2.4 Recommendations

| Feature | Status |
|---|---|
| Ranked recommendation page | ✅ `/recommendations` |
| Every item carries an explanation | ✅ 8/8 verified rendering a reason |
| Festival urgency badge | ✅ *Required for Dashain in 18 days* |
| Personalisation from order history | ✅ |
| Stable ordering across requests | ✅ Deterministic sort key |

See `docs/AI-RECOMMENDATION.md`.

### 2.5 Reviews and ratings — *built Day 11*

| Feature | Status | Notes |
|---|---|---|
| Average rating + star display | ✅ | `—` and "No reviews yet" for an unrated product, never `0.0` |
| 5-to-1 distribution bars | ✅ | Computed from the same response |
| Review list | ✅ | Paginated; "Show more" walks `?page=` |
| Write a review | ✅ | Star picker, title, body; publishes immediately |
| Edit / delete your own | ✅ | The form prefills, so editing does not mean retyping |
| One review per customer per product | ✅ | A second submission **edits** the first |
| Verified-purchase badge | ✅ | Shown when the account had ordered the product before reviewing |
| Privacy in a public list | ✅ | `author` is a display name (`Ram S.`); no username, no email |
| Rating line under the product title | ✅ | Updated in place after a write, without refetching the product |
| Dashboard moderation | ✅ | `/reviews` — Hide / Show / Delete, with a search across product, reviewer and wording |

**No pre-moderation.** A review publishes the moment it is written and a manager hides it
afterwards. Every review being invisible until somebody looks is indistinguishable from the
feature not working, on a demo with nobody on duty. Hide is reversible; the delete dialog
says so and points at it.

### 2.6 Samagri search — *rebuilt Day 12*

The sixth discovery entry point, and the one that was weakest. Full detail in
`docs/SEARCH.md`.

| Feature | Status | Notes |
|---|---|---|
| Relevance ranking | ✅ | Name match tier, then position within the name, then popularity as a tie-break only |
| Transliteration | ✅ | `sindur` finds *Sindoor Powder*; `deep` finds *Brass Diyo*; `karpoor` finds *Camphor (Kapur)* |
| **Search by ritual or festival name** | ✅ | `pasni` returns the 9 samagri of the ritual and its kit — none of them named after it |
| Required vs optional | ✅ | The reason says *Required for Pasni (rice-feeding ritual)* or *Optional extra for … (kit)* |
| Every result explains itself | ✅ | A machine-readable code and a human sentence per match, rendered on the card |
| Alternative spellings reported | ✅ | "Also searched for sindhur, sindoor, sindor, vermilion" |
| "Did you mean" on a typo | ✅ | Clickable suggestions drawn from the catalogue's own vocabulary |
| "Keep typing" vs "no match" | ✅ | Two different messages, because they are two different things |
| Shareable search URL | ✅ | `/products?q=sindur` loads directly |
| Category filter during search | ✅ | Narrows the candidate set before ranking |
| Catalogue paging | ✅ | "Show more" walks `?page=`; it used to show 12 of 35 with nothing saying so |

**What it replaced, measured.** `sindur`, `dhup`, `deep`, `karpoor`, `sankha`, `nariyal` and
`agarbati` all returned **zero** products; `pasni` and `griha pravesh` returned **zero**
although both are seeded rituals with complete kits; and `diyo` ranked *Cotton Wicks* above
*Brass Diyo (Oil Lamp)*.

> `?search=` on the list endpoints is **unchanged** — the dashboard's item picker depends on
> it and wants a plain substring match over one vendor's stock, which is a different job.

---

## 3. Admin dashboard (`admin-dashboard`, :3001)

### 3.1 Access control

| Feature | Status | Notes |
|---|---|---|
| Login gate | ✅ | Verifies the token against `/auth/profile/`, not just its presence. Gates on the **resolved role**, so all three staff roles get in |
| Role-aware navigation | ✅ | Manager-only items hidden from vendors |
| Role badge in the sidebar | ✅ | Super Admin / Administrator / Vendor |
| Client-side guard | ⚠️ | A **UX guard only** — every action is enforced server-side |

### 3.2 Management screens

| Screen | Status | Capabilities |
|---|---|---|
| Dashboard | ✅ | KPIs, priority alerts, revenue chart |
| Products | ✅ | **Create · Edit · Delete · Enable/Disable**, search, stock badges |
| Orders | ✅ | List, filter, change status; vendor-scoped |
| Festival Kits | ✅ | **Create · Edit · Delete · Enable/Disable**, search, and an **inline item editor** — add a product, set its quantity and its required/optional flag, remove it |
| Rituals (Pujas) | ✅ | Same screen shape as kits, from one shared component. Create · Edit · Delete · Enable/Disable, inline samagri editor |
| Vendors | ✅ | **Create · Edit · Delete · Enable/Disable**, assign a delivery area, search. Creating a shop promotes its account to the vendor role |
| Demand Forecast | ✅ | Restock table, sparklines, MAPE, per-row "Why?" |
| **Reviews** | ✅ | **Added Day 11** — Hide · Show · Delete, search by product/reviewer/wording. No Create and no Edit, by design |
| **Catalog Settings** | ✅ | Categories CRUD + Delivery Areas CRUD with fee overrides |

**The item editor is deliberately not paginated.** It is the body of an editor, not a
browsable table: Bratabandha has 14 items and Daily Puja has 21, while the project-wide
`PAGE_SIZE` is 12. Paginated, the editor would have silently shown an incomplete kit
and an admin would have had no way to tell. Two tests build 14 rows and assert a bare
list, because a `results` dict would still pass a `len()` check against a page.

**Item rows are editable in place.** Both detail views are
`RetrieveUpdateDestroyAPIView`, not delete-only — otherwise changing a quantity from 1
to 2 means deleting the row and re-adding it, which also churns its id.

### 3.3 Four-state handling

Every async surface shows **loading · success · empty · error**:

| Surface | Loading | Empty | Error |
|---|---|---|---|
| Products table | skeleton rows | "No products… use New Product" | message + Try again |
| Kits / Rituals table | skeleton rows | "No kits yet. Use New Kit…" | message + Try again |
| Expanded item editor | skeleton rows | "No items yet. Search above to add…" | message + Retry |
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
| Open the admin dashboard | ❌ | ✅ | ✅ | ✅ |
| Analytics | ❌ 403 | ✅ *12 products* | ✅ *35* | ✅ |
| Manage products | ❌ 403 | ✅ *own only* | ✅ | ✅ |
| Manage orders | ❌ 403 | ✅ *own only* | ✅ | ✅ |
| Categories (read / write) | ❌ / ❌ | ✅ / ❌ | ✅ / ✅ | ✅ |
| Kits, rituals + their items (read / write) | ❌ / ❌ | ✅ / ❌ | ✅ / ✅ | ✅ |
| Areas, vendors (write) | ❌ | ❌ | ✅ | ✅ |
| Assign a product to any vendor | ❌ | ❌ | ✅ | ✅ |
| Enumerate user accounts | ❌ | ❌ | ✅ | ✅ |
| Grant the vendor role | ❌ | ❌ | ✅ | ✅ |

Enforced in `get_queryset()`, not the UI. A vendor requesting another vendor's
object gets **404**, not 403 — no existence leak. The user-account list is the one
endpoint where *reading* is itself a privilege, so it uses `IsManager` rather than
`IsManagerOrReadOnly`.

**Verified:** 64 unit tests + 55 live assertions (`verify_day3.py`), plus 49 more in
`verify_day9.py` covering the vendor-administration paths.

> The dashboard gate is the **resolved role**, not the legacy `is_admin_user` boolean.
> Gating on that boolean meant a vendor's token verified, came back `false`, and was
> discarded — the VENDOR role was enforced correctly on every endpoint and could not
> reach a single screen. See `docs/CURRENT-STATE.md` Day 9.

---

## 6. What is NOT built

Honest list of gaps, so nothing here is mistaken for finished work.

| Feature | Status | Impact |
|---|---|---|
| Payment gateway | ❌ | `esewa`/`khalti` are **mocked** — they just mark the order paid |
| Reviews / ratings | ✅ | **Built on Day 11** — see §2.5. Removed from this list |
| Wishlist | ❌ | — |
| Vendor self-service UI | ✅ | **Built on Day 9** — a vendor logs into the dashboard and sees its own products, orders and forecast, with manager-only screens hidden |
| Kit / ritual editor UI | ✅ | **Built on Day 8** — kits and rituals are fully authorable, including their item lists |
| Email / SMS notifications | ❌ | Reset mail sends (console backend in dev); no order notifications |
| Real sales data | ❌ | Forecast trains on synthetic data; order volume is too low to train on |
| Search relevance tuning | ✅ | **Rebuilt Day 12** — see §2.6. Remaining gaps are listed honestly in `docs/SEARCH.md` §7 |
| Image upload UI | ⚠️ | Kits and products have an `image` column, but no upload widget in either dashboard screen — `image` is deliberately not in the kit write payload |
| Order history for pre-Day-4 orders | ⚠️ | Backfilled with a single event, so their earlier steps show "not recorded" rather than an invented time |
| Festival-specific kits | ⚠️ | 3 of the 6 soonest festivals have no kit (Ganesh Chaturthi, Haritalika Teej, Indra Jatra). The home page says so plainly and routes to the recommender |
| Linking a kit to a ritual from the ritual side | ⚠️ | By design: the FK is on the kit (`FestivalKit.puja`), because a kit declares which ritual it serves and one ritual may have several bundles. The kits page sets it; the rituals page reports it read-only |

### Fixed on Day 12 (2026-09-21)

| Issue | Detail |
|---|---|
| **The Samagri entry point could not spell.** Seven common transliterations returned zero products | `sindur`, `dhup`, `deep`, `karpoor`, `sankha`, `nariyal` and `agarbati` all returned **0**. See §2.6 and `docs/SEARCH.md`. |
| **Two seeded rituals returned nothing when searched by name** | `pasni` and `griha pravesh` returned **0** products, although both have a complete kit. No product is named after a ritual, so a substring match over `Product.name` could not see the `PujaItem` / `KitItem` link at all. |
| **`diyo` ranked *Cotton Wicks* above *Brass Diyo (Oil Lamp)*** | Results came back in `-popularity_score` order, not by how well they matched. Fixed with a name-position signal; popularity is now a tie-break only. |
| **The catalogue showed 12 of 35 products and implied that was all of them** | The page fetched page 1 and rendered it as the whole catalogue. Same trap as the dashboard's item editor: a silent truncation that looks correct. Now a "Show more" that walks `?page=` and says how many are left. |
| **`ToastContext` re-created its callbacks on every render** | `success`/`error`/`info` were bare arrow functions in an inline object literal. Any consumer that put `error` in a `useCallback` dependency list would re-create its own callback on every render and re-fire the effect that depends on it — the same unbounded loop that hit the reviews section on Day 11. Fixed at the root, with `useCallback` and a memoised value. |
| **The products page nested a `<main>` inside the layout's `<main>`** | Invalid HTML, and ambiguous for a screen reader — "go to main content" stopped having one answer. Now a `<div>`. |
| **A plain function named `useSuggestion`** | The `use` prefix made ESLint treat it as a React hook, so calling it from a click handler was a `rules-of-hooks` error. Caught by lint; renamed. |

### Fixed on Day 11 (2026-09-21)

| Issue | Detail |
|---|---|
| **The product page refetched its reviews forever** | `ReviewsSection`'s load effect had `onSummaryChange` in its dependency list, and the page passed it as an inline arrow — a new function on every render. So `load → setState in the parent → re-render → new arrow → new load → load` never settled: **537 requests to the reviews endpoint in 12 seconds**, still climbing, with the section flickering between skeletons and content. The build, ESLint, 336 unit tests and 575 live API assertions all missed it; the new browser assertion for the review flow surfaced it as *flakiness*, and it took a request counter to prove it. Fixed on both sides — the component now holds the callback in a ref (safe by construction), and the page passes a stable `useCallback` that bails out when the numbers have not moved. Now **1 request per page load**. |
| **`<slug:slug>/reviews/` 404'd the entire admin review API** | `admin` is a valid slug, so the public route matched `admin/reviews/` with `slug='admin'`, found no such product and returned 404 — for managers, customers and anonymous readers alike. Five of six test failures were this one bug. See the route-ordering rule in `docs/API-SPEC.md` §2. |

### Fixed on Day 10 (2026-09-21)

Found by driving the storefront in a real browser — none of these were visible to the
build, to lint, or to 575 live API assertions.

| Issue | Detail |
|---|---|
| **A full page load of `/checkout` bounced to `/cart`** | Even with a full cart. Refresh, bookmark and shared link all failed. The guard read `!loading && cartItems.length === 0`, which is also true *before* the cart has been fetched — so it could not tell "empty" from "not fetched". Arriving from `/cart` hid it, because that is a client-side route change and the provider does not remount. |
| **A successful checkout sent the customer to an empty cart** | The order *was* placed. `handleSubmit` emptied the cart before pushing to the confirmation, and the guard watching for an empty cart `replace`d to `/cart` — racing the push. Reads as "it didn't work", so people order twice. |
| **"My Orders" linked to a route that did not exist** | The account dropdown has pointed at `/account/orders` since the menu existed, and there was no page behind it. `/account` shows the five most recent orders, so it was never the destination the label promised. Now a real page. |
| **`/cart` told a customer with items their cart was empty** | Briefly, on every fresh load. Same root cause as the checkout bounce. |

The fix for the first three is one idea: **a loading flag is not a loaded flag.**
`CartContext` now exposes `cartLoaded` — true once the cart state reflects the signed-in
user — and a failed fetch deliberately does not set it, so a backend blip cannot
masquerade as an empty cart. `/checkout` also claims its redirect (`placed`) before
emptying the cart.

### Fixed on Day 9 (2026-09-21)

| Issue | Detail |
|---|---|
| **A vendor could not log into the dashboard at all** | `AdminContext` gated on `is_admin_user`, a legacy boolean only ever set for super_admin/admin. The token verified, came back `false`, and the login bounced. The VENDOR role was correct on every endpoint and unreachable in the product. |
| **`/auth/profile/` published the raw `role` column** | `get_role()` falls back to `is_staff` for legacy accounts, so the API was telling the dashboard "customer" while authorising as "admin". It now publishes the resolved role. |
| **No vendor management screen** | The vendor API worked and nothing called it — shops could only be created in Django admin. Now `/vendors`, with area assignment. |
| **No way to choose the account a shop belongs to** | `Vendor.user` is a `OneToOneField`, so the form needed a picker. `GET /api/auth/admin/users/` is manager-only, because enumerating people is a privilege a vendor must not have. |
| **"Add a vendor" left the account a customer** | The `Vendor` row does not make an account a vendor — the role does. Creating a shop now promotes it, without granting Django admin (`is_staff`). |
| **Two "role is read-only" guards proved nothing** | Both hit the wrong verb and path (`PATCH /api/accounts/profile/`, which does not exist) and passed against a 404/405. Both now drive `PUT /api/auth/profile/` and assert the write landed. |
| **A vendor creating a product saw "Your shop", not their shop's name** | Found in the browser, not by any API test. The read-only field was left blank on create. |

### Fixed on Day 8 (2026-09-21)

| Issue | Detail |
|---|---|
| **The dashboard could show the puja domain but not edit it** | `/festivals` made no write calls at all, so the ready-made kits — a headline feature — could only be assembled in Django admin at `/admin/`. |
| **`/pujas` did not exist in the dashboard** | The whole ritual half of the domain was unreachable from the product's own management UI. Now built, from the same component as the kits page. |
| **Item rows were delete-only** | Changing a quantity meant deleting the row and re-adding it, which also churned its id. Both detail views are now `RetrieveUpdateDestroyAPIView`. |
| **Item lists inherited `PAGE_SIZE = 12`** | Bratabandha has 14 items and Daily Puja has 21, so the editor would have silently shown an incomplete kit and looked fine. Both lists are now unpaginated, pinned by tests that assert a **bare list**. |
| **The festival type dropdown would have been derived from the kits that exist** | Same trap as the old hardcoded `CITY_CHOICES`, in reverse — a type with no kit yet could never be chosen, so the first kit of a new type could not be created. `GET /api/festivals/choices/` publishes the enum itself. |
| **`FestivalKitAdminSerializer` was `fields = '__all__'`** | It leaked `image` — a file upload a JSON form cannot set — and did not reliably carry `item_count`, which the new kits table shows. |
| **A full-width panel row would have broken on narrow screens** | Below 720px the tables pin their first column and set `white-space: nowrap` on every cell, which would have pinned the item editor and stopped it wrapping. New global `.table-panel` rule opts out. |

### Fixed on Day 7 (2026-09-19)

| Issue | Detail |
|---|---|
| **A password reset did not end existing sessions** | Documented as a known limitation on Day 4: access tokens are stateless and last a day, so a stolen one kept working. Now every token carries a version claim checked on every request, and a reset bumps it. |
| **`token/refresh/` would keep serving a revoked user** | Found by the test suite. The refresh endpoint never goes through DRF's authentication classes, so a version check in the authentication class alone left it answering 200 and minting access tokens. |
| **No remedy for "someone else is logged in as me"** | Logging out only discards the token the current device holds. `POST /auth/logout-all/` revokes everything. |
| **A signed-out visitor got "Session expired. Please login again."** | `ProductCard`'s `+` sent the request regardless. It now routes to login and returns to the product afterwards. |

### Fixed on Day 6 (2026-09-19)

| Issue | Detail |
|---|---|
| **One of the six required discovery entry points did not exist** | `AGENTS.md` §1 requires Product · Category · Festival · **Puja** · Samagri · Ready-made Kit. Puja had no model, endpoint or page at all. |
| **`festival_type` conflated festivals and rites of passage** | It held `dashain`/`tihar`/`shivaratri` *and* `bratabandha`/`pasni`/`griha_pravesh`/`shraddha`. Two of its own labels end in "Puja". The `Puja` model untangles them. |
| **No way to buy what a ceremony needs without a kit** | `POST /orders/cart/add-puja/<id>/` adds the essentials and reports anything it skipped rather than silently under-filling the order. |
| **An unknown slug fell through to a bare default 404** | Now a styled app-wide `not-found.js`, and `notFound()` for an unknown ritual. |
| **`params` destructured without `await`** | Next 16 makes `params` a Promise. Destructuring it directly yields `undefined` — every valid ritual would have 404'd, and the build would not have caught it. |

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
25. Back to admin → Festival Kits → **Items** on a kit: add a product, set its
    quantity, flip Required/Optional, remove it
26. Rituals → create one, add samagri, then delete it
27. Vendors → create a shop for an account: the account becomes a vendor and can
    then log in
28. Vendors → assign a delivery area, then Edit again: the area is changeable but
    the owning account is frozen
29. Back to the storefront → a product page → **Ratings & Reviews**: write one, watch
    the average and the distribution move, and the "✓ Verified purchase" badge appear
    on a product you have ordered
30. Edit your review → change the stars → the summary follows. Delete it → the section
    goes back to "No reviews yet"
31. admin :3001 → **Reviews** → Hide a review, then reload the storefront page: it is
    gone and the average has moved. Show it again
32. Products → search **`sindur`** (not "sindoor"): it finds Sindoor Powder and the card
    says *matched on the alternative spelling "sindur" → "sindoor"*
33. Search **`pasni`** — a ritual, not a product. Nine samagri come back, each card saying
    *Required for Pasni (Rice Feeding)*, and the page names the ritual it matched
34. Search **`diyo`**: the lamps rank above "Mustard Oil for Diyo", and above the wicks
    that merely mention it in a description
35. Search **`sindoer`** (a typo): "Did you mean" with clickable corrections
36. Search **`x`**: "Keep typing", not "No products found"
37. Copy the URL from step 32 into a new tab — the search is shareable
38. Back on the catalogue with no query → **Show more**: it walks past the first 12
    products instead of pretending 12 is the whole catalogue
```

> The reviews page has no **New review** button and no **Edit** control, deliberately: a
> manager moderates reviews, they never write or rewrite them. Hiding is the reversible
> action and the delete dialog says so.

**Demo credentials:** `admin/admin123` (super admin) · `vendor1/vendor1234` (vendor)
· `testuser/test1234` (customer)

> Steps 27–28 consume an account: creating a shop promotes whatever login you choose,
> and deleting the shop does not demote it. Use `testuser` only if you are willing to
> promote the demo customer, or register a throwaway account first.

> Note: the reset in step 13 changes a demo password. Use the customer account, and
> either set it back to `test1234` afterwards or accept the new one for the rest of
> the session. `PASSWORD_RESET_EXPOSE_LINK` must be `False` in any real deployment.
