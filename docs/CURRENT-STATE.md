# CURRENT-STATE.md

Analysis date: 2026-09-18
Method: full source inspection + live server probing.
Last updated: 2026-09-21 (**Day 12 complete** — domain-aware search. Days 11 and earlier are
complete.)

---

## Day 12 Completed (2026-09-21) — the Samagri entry point, rebuilt

**Theme:** `AGENTS.md` §1 requires discovery through **six** entry points, and **Samagri** —
search — was the weakest of them. It was DRF's `SearchFilter` with
`search_fields = ['name', 'description']`, which is to say `icontains`. Three failures, all
measured against the seeded catalogue before anything was written:

| Failure | Evidence |
|---|---|
| **Transliteration** | `sindur` returned **0** products (the product is "Sindoor Powder"). Same for `dhup`, `deep`, `karpoor`, `sankha`, `nariyal`, `agarbati` — seven zero-result queries, each a spelling a shopper would plausibly type. |
| **The domain was not searchable** | `pasni` returned **0**, `griha pravesh` **0**, `bratabandha` **1** (a description match). `pasni` and `griha pravesh` are seeded rituals with complete kits — no product is named after a ritual, so a substring match over `Product.name` could not see the `PujaItem` / `KitItem` link at all. |
| **No ranking** | Results came back in `-popularity_score` order, so `diyo` ranked *Cotton Wicks* and *Pure Cow Ghee* above **Brass Diyo (Oil Lamp)**. |

**Verification: 379 unit tests + 727 live assertions + 143 browser assertions.**

| # | Piece | Status |
|---|-------|--------|
| 1 | `products/search.py` — normalisation, synonym groups, the domain index, tiered scoring, suggestions | **DONE** |
| 2 | `GET /api/products/search/?q=` — ranked, explainable, paginated, `?category=` aware | **DONE** |
| 3 | 41 unit tests, asserting ordering and explanation rather than shape | **DONE** — 379 total |
| 4 | `verify_day12.py` — 84 live assertions | **DONE** |
| 5 | Storefront search surface — shareable URL, match reasons, suggestions, "keep typing" | **DONE** |
| 6 | Catalogue paging — "Show more" walks `?page=` | **DONE** — it showed 12 of 35 and implied that was all |
| 7 | 19 new browser assertions | **DONE** — storefront 60 → 79 |
| 8 | `docs/SEARCH.md` + `FEATURES.md`, `API-SPEC.md`, `AGENTS.md`, `README.md` | **DONE** |

### The bug inside the bug: two ranking defects my own smoke test exposed

Both came from building the synonym index by splitting multi-word group members into their
component words — which looks harmless and is not:

- the group `('thali', 'plate', 'puja plate', 'tray')` registered **`puja` as a synonym of
  `thali`**, so searching "puja" returned plates and trays;
- the group `('dhoop', 'dhup', 'dhoop batti')` registered **`batti`**, so "dhup" returned
  *Cotton Wicks*.

A third: the phrase variant "oil lamp" was credited at the position of its first word, so
*"Mustard Oil for Diyo"* collected an early-match bonus it had not earned and stayed above
*Brass Diyo*. Fixed by never splitting group members, matching multi-word members as phrases,
and scoring position from single-word variants only. `SynonymIsolationTests` guards all three.

> None of this would have surfaced from reading the code. It surfaced from printing the top
> three results for twenty queries and looking at them.

### The frontend trap worth remembering

**`router.replace()` is a no-op when only a search-param *value* changes** on a statically
prerendered route. Measured on `/products`: `/products` → `/products?q=pasni` worked, but
replacing `?q=sindoer` with `?q=sindoor` produced no RSC request and no URL change at all — the
page showed results for "sindoor" while the address bar still read "sindoer". The no-query case
working is exactly what made it look fine. Client-side filter state now uses
`window.history.replaceState`, the documented way to update search params from a Client
Component.

Also fixed on the way through: `ToastContext` was handing out **unstable callbacks**
(`success`/`error`/`info` as bare arrows in an inline object literal) — the same
`useCallback`-dependency hazard that caused the Day 11 fetch loop, fixed at the root so no
consumer has to remember. And the products page nested a `<main>` inside the layout's `<main>`:
invalid HTML, and ambiguous for a screen reader.

### Two verifier defects in `verify_day11.py`, found by running it in a normal order

The Day 11 verifier had never been run *after* the storefront browser check. Doing so failed
two checks — and both were the verifier's fault:

- It asserted "the verified-purchase badge is false before any order" about `testuser`.
  `testuser` already had an order for that product, because the browser check buys the most
  popular one. **The feature was right; the verifier was asserting about an order history it
  did not own.** Both badge checks now run as a throwaway account the script registers itself,
  and in the order that makes the badge known to be false.
- The read-only-badge check borrowed whichever review was handy, including one whose badge was
  already `True` — so it could not have detected the regression it exists for. It now runs
  before the purchase, on a review this script owns.

`verify_day11.py` is now order-independent: **68/68 twice in a row with leftover state.** The
general rule is written into `AGENTS.md` §12.

### Resume with

```bash
cd backend && ./venv/Scripts/python.exe manage.py test        # 379 tests, all green
./venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
./venv/Scripts/python.exe verify_day12.py                     # 84 assertions
```

---

## Day 11 Completed (2026-09-21) — reviews, and a fetch loop only a browser could see

**Theme:** the last P1 item the brief names by omission. `docs/DATABASE-DESIGN.md` said
"no `Coupon` / `Review` / `Wishlist` tables — not in scope; noted as post-MVP", and
`FEATURES.md` listed "no social proof on product pages" as a gap. Both are now closed for
reviews.

**Verification: 336 unit tests + 641 live assertions + 124 browser assertions.**

| # | Piece | Status |
|---|-------|--------|
| 1 | `Review` model in `products` — one per (product, user), `is_approved`, `is_verified_purchase` snapshot | **DONE** — migration `products/0005_review.py`, applied |
| 2 | Django admin registration, with the verified badge read-only | **DONE** |
| 3 | `average_rating` / `review_count` on the product detail, from queryset annotations | **DONE** — `with_review_summary()`; 3 queries regardless of review count |
| 4 | `GET`/`POST /api/products/<slug>/reviews/` — public list + summary + `mine`, create-or-update own | **DONE** |
| 5 | `DELETE /api/products/reviews/<id>/` — own, or any as a manager | **DONE** |
| 6 | `GET /api/products/admin/reviews/` + `/admin/reviews/<id>/` — manager-only, unpaginated | **DONE** |
| 7 | 25 unit tests (write, summary, privacy, verified purchase, deletion, moderation, query count) | **DONE** — 336 total, all passing |
| 8 | Storefront reviews section on `/products/[slug]` | **DONE** — `ReviewsSection.js` |
| 9 | Dashboard `/reviews` moderation screen | **DONE** — a `DomainManager` config, not a fork |
| 10 | `purge_verification_reviews` command | **DONE** — a stray review would silently change a seeded product's rating |
| 11 | **`verify_day11.py` run** | **DONE — 66/66.** Two of its own assertions were wrong and were fixed, see below |
| 12 | **Browser assertions for the review flow** | **DONE** — storefront 14 new, dashboard 14 new. They found a real bug, see below |
| 13 | **Docs** | **DONE** — `FEATURES.md`, `API-SPEC.md`, `DATABASE-DESIGN.md`, `AGENTS.md`, `README.md`, this file |

### The bug the new browser assertions found — a fetch loop on the product page

The review UI compiled, rendered, and passed every API test. It also **hammered the API**:

```
537 requests to /api/products/<slug>/reviews/ in 12 seconds, still climbing
```

`ReviewsSection`'s load effect listed `onSummaryChange` as a dependency, and the product
page passed it as an inline arrow — a new function identity on every render. That is an
unbounded loop:

```
load() → onSummaryChange() → parent setState → parent re-render →
new arrow → new `load` identity → effect fires → load() …
```

**Nothing else could see it.** The build passed, ESLint passed, 336 unit tests passed and
575 live API assertions passed. It surfaced as *flakiness* in a check written minutes
earlier — the same assertion passed, failed, then passed again on three identical runs.

That is the finding worth carrying forward: **a check that "usually passes" is a bug
report, not noise.** The instinct to re-run past an intermittent failure would have shipped
this.

Fixed on both sides, and both halves matter:

- `ReviewsSection` holds the callback in a `useRef`, so it is safe by construction and no
  caller can reintroduce the loop;
- the page passes a `useCallback` whose state update returns the previous object when the
  values have not moved, so it does not re-render for nothing.

`storefront_check.mjs` now pins it with a request counter across two five-second windows —
one fetch per load is correct, anything that keeps growing is not.

This is the same trap the project already documented for `DomainManager` ("the config must
be a module-level constant — it is a `useCallback` dependency, so an inline literal
re-fetches forever"). `AGENTS.md` §5 now states the general rule.

### Two assertions in `verify_day11.py` were wrong, and the fix is the lesson

Both failures on the first run were the verifier's own expectations, not the code:

- **"the verified badge cannot be rewritten by a manager"** picked a review whose badge was
  already `True`, so `is not True` failed whether or not the write was honoured — the check
  could not have detected a real regression. It now finds an **unverified** review, tries to
  verify it, and asserts it stayed `False`, with a re-read to confirm the write never landed.
- **"the average matches the review list"** hardcoded `3.0`, a number that went stale as
  soon as the script's own earlier section edited the review it was measuring. It now
  compares the product payload against the live review list.

> **Do not assert a literal you did not just read.** A guard that fails for the wrong reason
> is a bug report about the guard, not the code.

### The routing bug this feature produced

Adding `<slug:slug>/reviews/` **404'd the entire admin review API** — for managers,
customers and anonymous readers alike. `admin` is a valid slug, so the public pattern
matched `admin/reviews/` with `slug='admin'`, looked for a product called "admin", found
none and returned 404. The literal `admin/reviews/` route sat *below* it and never ran.
Five of six test failures were this one bug.

The project's note said "the slug detail route goes last". The real rule is **nothing with
a slug converter may sit above a literal path of the same depth**. `products/urls.py` is now
ordered public literals → admin → slug patterns, and carries that wording.

### Two design decisions worth keeping

- **`is_approved` defaults to `True`.** Auto-publish with a manager able to hide
  afterwards. Pre-moderation would mean every review is invisible until someone looks,
  which on a demo with no staff on duty is indistinguishable from the feature not working.
- **The admin review list is unpaginated**, matching every other admin collection here
  (kits, rituals, vendors). Paginated, a hidden review on page 2 would be invisible to the
  only person who can unhide it — the one-way door the flag exists to avoid. The *public*
  review list on a product page **is** paginated; that one is browsable content that grows.

### What the browser checks now cover

- **Storefront (60 assertions):** the section renders and is headed correctly; the product
  starts unreviewed (established, not assumed); the form opens; a rating with no words is
  refused **on screen**; a posted review appears in the list with a verified-purchase badge
  and a display name and no username or email; edit and delete work and return the section
  to its empty state; and the request counter above.
- **Dashboard (64 assertions):** the seeded review lists with its product and reviewer;
  there is **no** "New review" and **no** Edit control; Hide flips the badge and offers Show
  again; the flash confirms both directions; the delete dialog warns it cannot be undone and
  points at Hide; and a vendor reaching `/reviews` directly gets an error state with no
  rows **and stays signed in**, because a 403 that dumps you back on the login screen reads
  as a broken login rather than a permission boundary.

Both checks clean up after themselves. The dashboard seeds its review through the API (the
page deliberately cannot author one) and deletes it again; the storefront posts one and
deletes it through the UI.

### Resume with

```bash
cd backend && ./venv/Scripts/python.exe manage.py test        # 336 tests, all green
./venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
./venv/Scripts/python.exe verify_day11.py                     # 66 assertions
```

```bash
# Browser checks — production builds, ports pinned, started sequentially
cd frontend        && npm run build && npx next start -p 3000
cd admin-dashboard && npm run build && npx next start -p 3001
NODE_PATH=/tmp/harness/node_modules node scripts/storefront_check.mjs   # 60
NODE_PATH=/tmp/harness/node_modules node scripts/browser_check.mjs      # 64
```

---

## Day 10 Completed (2026-09-21) — the storefront, driven like a customer

**Theme:** Day 9 proved a green API suite cannot see a client-side render failure. The
admin dashboard got a browser check; **the customer storefront — the part that actually
gets demonstrated — had never been driven.** It has now, end to end, and it found three
real bugs. All three were invisible to the build, to lint, and to 575 live API
assertions.

**Verification: 295 backend unit tests + 575 live assertions + 83 browser assertions.**

| # | Bug | Severity |
|---|-----|----------|
| 1 | **A full page load of `/checkout` bounced to `/cart`** — even with a full cart. Refresh, bookmark and shared link all failed | **High** — the demo's most important page was unreachable by URL |
| 2 | **After a successful checkout, the customer was sent to the empty cart** instead of the confirmation. The order *was* placed | **High** — reads as "it didn't work", so people order twice |
| 3 | **"My Orders" in the account menu linked to a route that did not exist** | **Medium** — a nav item that 404s |
| 4 | `/cart` flashed "Your cart is empty" at a customer who had items | Low — wrong thing said, briefly |

### 1. `/checkout` was unreachable by URL

`CartContext`'s `loading` flag starts `false`, and the cart is empty until the first
fetch resolves. The checkout guard asked:

```js
if (authLoading || cartLoading) return;
if (cartItems.length === 0) router.replace('/cart');
```

"Not loading" and "no items" are both true *before* the cart has been fetched, so a
direct load redirected a customer with a full cart to their cart. It only ever worked
when arriving from `/cart` — a client-side route change, where the provider does not
remount and the items are already in state. **The happy path hid it completely.**

The fix is not a longer timeout. The cart now reports whether it has actually loaded
**for the current user**:

```js
// undefined = nothing loaded yet · null = loaded, nobody signed in · id = loaded for them
const [loadedForUserId, setLoadedForUserId] = useState(undefined);
// …
cartLoaded: loadedForUserId === (user ? user.id : null)
```

A failed fetch deliberately leaves it untouched, so a backend blip cannot masquerade as
an empty cart — the same bug wearing a different hat. `cartLoaded` also fixed the
`/cart` flash.

### 2. The order was placed, and the customer never saw it

`handleSubmit` did the right things in the wrong order:

```js
const order = await ordersAPI.checkout(formData);
await loadCart();                        // the cart is now empty
router.push(`/account/orders/${order.id}`);
```

Emptying the cart re-ran the guard above, which `replace`d to `/cart` — racing the
`push` to the confirmation. The customer's order existed and they were looking at an
empty cart, which reads as a failed checkout.

Confirmed rather than assumed: the order row was real (`id=77`, Rs. 2685, the harness
marker in `notes`). The fix claims the redirect before emptying the cart:

```js
setPlaced(true);        // the guard stands down
await loadCart();
router.push(`/account/orders/${order.id}`);
```

and the page says "Order placed — taking you to your order…" while that happens,
instead of flashing a form with nothing in it.

### 3. A nav link to nowhere

`Navbar` has linked to `/account/orders` since the account menu existed, and there was
no page behind it — **My Orders** landed on the 404. `/account` shows the five most
recent orders under the heading "Recent Orders", so it was never the destination the
label promised.

`src/app/account/orders/page.js` now exists: the full history, paginated by walking
`?page=` (`ordersAPI.listPage`) rather than showing the first page and implying it is
everything — the same trap as the paginated item lists in the dashboard. The account
page also gained a "See all →" link.

A link to a missing route compiles fine, returns a healthy page, and only misbehaves
when a person clicks it. That is the whole argument for this pass.

### 4. Verifier bugs found while writing the verifier

- **`textContent()` includes the RSC payload** embedded in `<script>` tags, so a check
  can pass on data that was never rendered — the ritual page's "Essential" assertion
  was reading flight data off a page still showing skeletons. Now `innerText()`, which
  is rendered text only.
- **`innerText` reflects CSS `text-transform`.** A check for `'Next festival'` failed
  because the eyebrow is uppercased in the stylesheet. Case-insensitive now.
- **A client-side nav updates the URL before the Server Component renders**, so waiting
  on the URL alone reads the loading fallback. The ritual-detail check now waits for the
  samagri list itself.

### 5. What the storefront check covers

`frontend/scripts/storefront_check.mjs` — **44 assertions**, driving the real Edge:

```
home → signed-out guard → login → cart is empty (established, not assumed)
     → /festivals → /pujas → /pujas/<slug> → add essentials
     → /products → product detail → add to cart
     → /cart (totals + delivery fee) → /checkout (full page load!)
     → order confirmation (timeline, area, total) → /account → /account/orders
     → /recommendations → cart is empty again → no console errors
```

The total is the check worth having: it reads the figure the checkout button promises
(`Place Order (Rs. X)`) and holds the recorded order to it. A hardcoded client-side
delivery fee once made those disagree — that bug is why the fee is served from
`GET /orders/config/` at all.

It places **one real order**, marked in `notes` as `browser_check.mjs` so
`purge_verification_orders` sweeps it up. That marker was added to the command in this
pass; the command also clears cart lines.

### Verification after Day 10

| Suite | Result |
|---|---|
| `manage.py test` | 295 pass — no regression |
| `verify_day2.py` … `verify_day9.py` | 575 live assertions — no regression |
| `admin-dashboard/scripts/browser_check.mjs` | **39/39** — no regression |
| `frontend/scripts/storefront_check.mjs` | **44/44** — new |
| **Browser assertions** | **83** |

- Customer storefront builds clean, **14/14 pages** (was 13 — `/account/orders` is new).
- Admin dashboard builds clean, 12/12 routes.
- `npx eslint --rule '{"no-undef":"error"}' src/` — no undefined identifiers in any file
  this pass touched. The frontend still carries 1 pre-existing `react-hooks` error and 8
  warnings in files that predate this work.
- Database restored to seeded state: 3 users · 35 products · 10 categories · 3 areas ·
  1 vendor · **8 orders** · 20 order items · 0 cart lines · 8 status events · 7 kits ·
  67 kit items · 8 rituals · 88 ritual items · 10 active future festivals ·
  13,600 synthetic rows.

### Known limitations, recorded rather than hidden

**The harnesses are not wired into any script.** They need `playwright-core` installed
outside the project — deliberately not a `package.json` dependency, because adding one
needs a reason and these are dev tools. Both are documented in `AGENTS.md` §5.

**Neither harness covers the admin dashboard's write paths or the storefront's
authentication flows in depth.** They verify that pages render, that the documented
journeys complete, and that no client-side exception fires. The API verifiers remain the
authority on data correctness.

---

## Day 9 Completed (2026-09-21) — vendor administration, and a browser that found a bug

**Theme:** two gaps that no amount of API testing or linting could have surfaced.

`core/permissions.py` defines four roles, and the API has enforced vendor scoping
correctly since Day 3. But:

1. **A vendor could not open the dashboard.** Not "had a limited view" — could not get
   in at all. `AdminContext` gated on `is_admin_user`, a legacy boolean that
   `UserProfile.save()` only ever sets for `super_admin`/`admin`. A vendor's token
   verified, came back `false`, was discarded, and the login bounced straight back to
   `/login`. The VENDOR role was correct on every endpoint and unreachable in the
   product, which made it undemonstrable.
2. **There was no way to administer a vendor.** `/products/admin/vendors/` worked and
   nothing called it, so a shop could only be created in Django admin — and the screen
   that fixes that needed an account picker, which did not exist either.

**Verification: 295 backend unit tests + 575 live assertions + 39 browser assertions.**

| # | Was | Now |
|---|-----|-----|
| 1 | **A vendor could not log into the dashboard at all** | **FIXED** — the gate is the resolved role, not the legacy boolean |
| 2 | `/auth/profile/` published the **raw** `role` column, not the resolved one | **FIXED** — it publishes what `get_role()` enforces, so client and server agree |
| 3 | No vendor management screen | **BUILT** — `/vendors`: create, edit, assign area, disable, delete |
| 4 | No way to choose the account a shop belongs to | **BUILT** — `GET /api/auth/admin/users/`, manager-only |
| 5 | "Add a vendor" left the account a **customer** | **FIXED** — creating a shop promotes the account to `vendor` |
| 6 | Two "role is read-only" guards **proved nothing** | **FIXED** — both hit the wrong verb and path, so they passed against 404/405 |
| 7 | *(found in the browser)* A vendor creating a product saw "Your shop", not their shop's name | **FIXED** — the read-only field is prefilled |

### 1. The bug only a browser could find

Everything else in this project is verified through the API or the build output. Both
were green: `vendor1` was scoped to 12 of 35 products, refused on the admin surfaces,
and every route returned 200. The dashboard was simply **unusable by that role**, and
no API test can see a login bounce.

This is why a browser harness now exists. The project has shipped this class of bug
before — four `Catalog Settings` buttons that threw `ReferenceError` before their
dialog opened, and a home-page "+" that looked like add-to-cart and had no handler.
Both compiled cleanly and linted cleanly.

`docs/` has no record of browser verification ever having been run. It is now:

```
cd admin-dashboard && NODE_PATH=<harness>/node_modules node scripts/browser_check.mjs
```

39 assertions across sign-in, `/festivals`, `/pujas`, `/vendors`, the item editor, the
product search, and a second session as `vendor1`. It drives the Edge already on the
machine through `playwright-core`, so there is no Chromium download and **nothing is
added to `package.json`**.

### 2. The gate was the wrong question

`is_admin_user` asked *"is this an administrator?"*. The dashboard needs to ask *"may
this account use the dashboard?"* — and the server answers that with
`is_staff_role()`, which includes vendors. Gating on the legacy boolean conflated the
two.

The fix is not "add vendor to the boolean". It is to publish the **resolved** role:

```python
def get_role(self, obj):
    return get_role(obj.user)   # core.permissions — the single source of truth
```

That also closes a latent inconsistency. `get_role()` falls back to `is_staff` for
accounts created before roles existed, so a legacy staff user resolves to `admin`
server-side while the raw column still reads `customer`. The API was telling the
dashboard one thing and acting on another.

### 3. `DomainManager` gained three things, and none of them forked it

| Addition | Why |
|---|---|
| `itemsUrl` optional | A vendor owns products, not items. Omitting it drops the Items control entirely, rather than showing a panel that always says "no items" |
| `displayName(row)` | A `Vendor` has `shop_name`, not `name`. The edit title and delete confirmation needed a way to say the right thing |
| `createOnly` on a field | A shop's owning account is offered once and then frozen. Reassigning it would silently transfer everything that account owns |

`/vendors` is a config, not a page. The rule holds: a third collection with a list, a
form and items is another config.

### 4. Creating a shop now makes the account a vendor

`Vendor.user` points at an ordinary login, and the row alone does not make that
account a vendor — the role does. Without this, the form's own hint ("it must be a
vendor account") was a lie: the picker offered customers and nothing converted them.

`promote_to_vendor()` has two deliberate limits, both tested:

- **Only `customer` accounts are promoted.** A manager or super admin who owns a shop
  keeps their higher role; demoting them would silently remove access they have.
- **`is_staff` is not set.** It is tempting, because it used to be what let an account
  reach the admin API — but it also grants Django admin at `/admin/`, and a vendor has
  no business there. `IsStaffRole` resolves through `get_role()`, so the role suffices.

**Deleting a shop does not revoke the role**, and the confirmation says so. Closing a
shop and revoking a login are different decisions; conflating them would let removing
a shop lock someone out of the dashboard.

### 5. Two guards that proved nothing

Found while writing the test for role escalation:

| Guard | What it actually did |
|---|---|
| `core/tests_roles.py::test_customer_cannot_patch_own_role` | `PATCH /api/accounts/profile/` — a path that **does not exist**, and `ProfileView` implements `PUT`, not `PATCH`. It asserted "the role did not change" after a 404. |
| `verify_day3.py` privilege-escalation section | `PATCH /auth/profile/` → **405**. Same vacuous pass. |

Both now drive `PUT /api/auth/profile/` and assert the write **landed** (the first name
changes), so the role assertion cannot be satisfied by a request that never reached
the guarded code. `verify_day3` went 55 → 57 assertions. A guard test that cannot fail
is worse than no test, because it reads like coverage.

### 6. Verifier bugs found while writing the verifier

- **`first_name` is not in the nested profile object.** `UserSerializer` puts it at the
  top level. Reading it from `profile` returns `None` on a correct response, which
  reported "the write did not land" against a write that had landed.
- **A harness race.** `waitForSelector('.table-panel button')` resolved instantly
  against the item table's own *Remove* buttons, so the product-search check ran before
  the debounced search returned. It now waits for a result button specifically.
- **A harness assumption.** I asserted a vendor has no create button. It does — vendor
  self-service is the point, and `AdminProductListCreateView.perform_create` forces
  ownership. The real invariant is that a vendor never sees anyone else's stock, so the
  check now asserts every row's vendor column and that the form's shop field is fixed.

### Verification after Day 9

| Suite | Result |
|---|---|
| `manage.py test` | **295 pass** (was 268) — 27 new |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | **57/57** (was 55 — two vacuous guards replaced) |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| `verify_day4.py` | 88/88 — no regression |
| `verify_day6.py` | 40/40 — no regression |
| `verify_day7.py` | 30/30 — no regression |
| `verify_day8.py` | 74/74 — no regression |
| `verify_day9.py` | **49/49** |
| **Live assertions** | **575** |
| **Browser assertions** | **39** (new — first browser pass in the project) |

- Admin dashboard builds clean, **12/12 routes** (was 11 — `/vendors` is new).
- `npx eslint --rule '{"no-undef":"error"}' src/` — no undefined identifiers in the new
  code. One pre-existing error remains (see below).
- Database restored to seeded state: 3 users · 35 products · 10 categories · 3 areas ·
  1 vendor · 8 orders · 20 order items · 0 cart lines · 8 status events · 7 kits ·
  67 kit items · 8 rituals · 88 ritual items · 10 active future festivals ·
  13,600 synthetic rows · **0 scratch rows**.

### Known limitations, recorded rather than hidden

**`verify_day9.py` leaves one probe account behind by design** — it registers an account
to promote, because that is the flow being tested. Run
`manage.py purge_verification_users` afterwards; it matches the `verifyday` prefix.

**The browser harness lives outside the project.** `playwright-core` is not a project
dependency and must not become one (adding a dependency needs a reason, and the harness
is a dev tool). The script is reproducible from `AGENTS.md` §5; the one-time setup is a
`npm install playwright-core` in a scratch directory.

**`is_staff` is still `True` on the seeded `vendor1`.** That was true before this pass
and grants Django admin access at `/admin/` — which a vendor should not have. The role
system does not need it any more (`IsStaffRole` resolves through `get_role()`), so the
seeded flag is now vestigial rather than load-bearing. Left alone because changing it
would also change what the demo vendor can reach in Django admin, and that is a
deliberate decision rather than a cleanup.

**One pre-existing lint error remains and is not from this work.**
`react-hooks/set-state-in-effect` in `layout.js` (`useEffect(() => setOpen(false),
[pathname])` in `NavShell`, written on Day 3.4). It comes from the rule set that ships
with `eslint-config-next` 16.2.2 and fires on `npx eslint src/` independently of
`no-undef`. It does not affect the build.

---

## Day 8 Completed (2026-09-21) — domain authoring in the admin dashboard

**Theme:** the dashboard could *show* the puja domain but could not *edit* it.

`/festivals` made **no write calls at all** — verified by grep, not assumed. The
ready-made kits that are a headline feature of this project could therefore only be
created or assembled in Django admin at `/admin/`. `/pujas` did not exist in the
dashboard in any form, so the entire ritual half of the domain was unreachable from
the product's own management UI.

**Verification: 268 backend unit tests + 524 live assertions, all passing.**

| # | Was | Now |
|---|-----|-----|
| 1 | `Puja` had public read endpoints and **no write endpoints** | **DONE** — `AdminPujaListCreateView` / `AdminPujaDetailView` under `/api/festivals/admin/pujas/` |
| 2 | Item rows were **delete-only** (`DestroyAPIView`) | **DONE** — both upgraded to `RetrieveUpdateDestroyAPIView`; quantity and `is_required` are editable |
| 3 | Item lists inherited `PAGE_SIZE = 12` | **DONE** — `pagination_class = None` on both. Bratabandha has 14 items, Daily Puja has 21; the editor would have silently shown an incomplete kit |
| 4 | Shared editor component | **DONE** — `admin-dashboard/src/components/ItemManager.js` + `.module.css` |
| 5 | `/festivals` was still read-only | **DONE** — kit create/edit/delete/enable, with `ItemManager` wired in behind a **Show items** toggle |
| 6 | `/pujas` did not exist | **DONE** — built, reusing the same editor; added to the sidebar |
| 7 | No live verifier for the new endpoints | **DONE** — `verify_day8.py`, 74 assertions |
| 8 | Docs | **DONE** — this file, `FEATURES.md`, `UI-UX-SPEC.md`, `API-SPEC.md`, `AGENTS.md` |

### 1. One component, two pages

`ItemManager` already knew how to edit the rows behind a kit or a ritual. What was
missing was everything around it: the list, the form, the delete flow. Both pages need
the same six things, so they are `DomainManager` with two configs rather than two
pages:

```
/festivals  →  DomainManager({ ...KIT_CONFIG  })
/pujas      →  DomainManager({ ...PUJA_CONFIG })
```

The config is a **module-level constant** on purpose. It is a `useCallback` dependency
inside `DomainManager`, so an inline object literal would be a new identity on every
render and re-run the initial fetch forever. That is written down in the component's
docstring because it is not obvious from the call site.

The same reasoning as `ProductCard`: three product cards once drifted apart because
each page grew its own copy, and the home one ended up with a "+" button that had no
handler.

### 2. The vocabulary is published, not hardcoded

Both forms need the festival/ritual enum to populate a dropdown. Deriving it from the
kits that happen to exist would be the old hardcoded `CITY_CHOICES` trap **in
reverse**: a type with no kit yet would be missing from the list, so the first kit of
a new type could never be created.

So `GET /api/festivals/choices/` publishes `FESTIVAL_CHOICES` itself. It is public
because every label in it is already visible in the `festival_type_display` of the
public kit list — gating it would protect nothing. Four tests pin it, including
`test_it_includes_types_that_have_no_kit`.

### 3. A ritual cannot be given a kit, and the UI says so

The link is a FK **on the kit** (`FestivalKit.puja`), because a kit declares which
ritual it serves and one ritual may legitimately have several bundles. A singular
"kit" picker on the ritual form would therefore have to choose one arbitrarily.

Rather than add an ambiguous write field, the ritual form carries a note pointing at
the kits page, and the rituals table reports what is already attached via a read-only
`kit_names`. `AdminPujaKitReportingTests` pins that it stays read-only.

### 4. Two things the new code had to get right

**`FestivalKitAdminSerializer` was `fields = '__all__'`.** That leaked `image` — a
file upload a JSON form cannot set, so a client posting a string path there got a
confusing error for a field it never rendered — and a declared `item_count` is not
reliably picked up under `__all__`. It is now an explicit field list, which the kits
table needs anyway. Three tests pin it.

**The expanded item panel is a table row that is not a data row.** Below 720px
`globals.css` pins `.table-wrap`'s first column (`position: sticky`) and sets
`white-space: nowrap` on every cell. A full-width panel row would have inherited
both — pinned to the left edge and refusing to wrap, i.e. a broken editor on exactly
the screens where the dashboard was already fixed once. It opts out via a new global
`.table-panel` rule, which wins on specificity where a CSS-module class could not.

### 5. Verifier bugs found while writing the verifier

Both were mine, and both made a working product look broken:

- **The admin product list is paginated at 12.** The script took the first response,
  got 12 products, and reported 11 failures that were all the same mistake — a kit
  built from 12 products can never cross the 12-row boundary the item list is being
  tested against. It now walks the pages (`fetch_products`).
- **It asserted a precondition it had not created.** The kit section deactivates the
  kit to prove the storefront hides it; the ritual section then asserted the
  storefront *offered* it. `Puja.kit` deliberately skips inactive kits, so `None` was
  correct. The script now reactivates it first — and keeps the deactivated case as a
  real check, since "an inactive kit is not offered as a ritual's bundle" is worth
  pinning.

Same lesson as the Day 3.4 and Day 6 test bugs: assert what you established.

### Verification after Day 8

| Suite | Result |
|---|---|
| `manage.py test` | **268 pass** (was 257) — 11 new for the choices endpoint, the kit admin payload and `kit_names` |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | 55/55 — no regression |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| `verify_day4.py` | 88/88 — no regression |
| `verify_day6.py` | 40/40 — no regression |
| `verify_day7.py` | 30/30 — no regression |
| `verify_day8.py` | **74/74** |
| **Live assertions** | **524** |

- Admin dashboard builds clean, **11/11 routes** (was 10 — `/pujas` is new).
- `npx eslint --rule '{"no-undef":"error"}' src/` — no undefined identifiers in the
  new component or pages.
- Database restored to seeded state after the sweep: 3 users · 35 products ·
  10 categories · 3 areas · 1 vendor · 8 orders · 20 order items · 0 cart lines ·
  8 status events · 7 kits · 67 kit items · 8 rituals · 88 ritual items ·
  10 active future festivals · 13,600 synthetic rows · **0 scratch rows**.

### Known limitations, recorded rather than hidden

**Superseded on Day 9: the two new pages have now been verified in a real browser.**
This section originally recorded that no browser pass had been run — the `AuthGate`
renders "Checking your session…" during SSR, so `curl` cannot see past it, and no
browser automation was installed. That gap is closed: `scripts/browser_check.mjs` drives the
installed Edge and covers `/festivals`, `/pujas`, `/vendors` and the item editor. It
found a bug on its first run (a vendor could not log in at all — see Day 9).

What remains true is the *reason* the payload-contract assertions in `verify_day8.py`
are worth keeping: a missing key is a render-time `TypeError`, not a validation error,
and the build cannot catch it because the data is fetched at runtime.

**One pre-existing lint error remains and is not from this work.**
`react-hooks/set-state-in-effect` in `layout.js` (`useEffect(() => setOpen(false),
[pathname])` in `NavShell`, written on Day 3.4). It comes from the rule set that ships
with `eslint-config-next` 16.2.2 and fires on `npx eslint src/` independently of
`no-undef`. It does not affect the build. Left alone deliberately: it is unrelated to
this pass, and the fix (closing the drawer from the link handler, or deriving from the
previous pathname during render) changes navigation behaviour that should be verified
on its own.

---

## Day 7 Completed (2026-09-19) — closing the one security gap we had documented

**Theme:** Day 4 recorded a limitation instead of fixing it. This fixes it.

> Day 4, verbatim: *"Existing JWTs survive a password reset. Access tokens are stateless and
> last a day, so a stolen token keeps working until it expires. Real revocation needs a
> blacklist or a per-user token version — deliberately out of scope."*

That is a real hole: the usual reason to reset a password is that somebody else may have it.
A reset that leaves their token alive for 24 hours is not a reset.

**Verification: 257 backend unit tests + 450 live assertions, all passing.**

| # | Was | Now |
|---|-----|-----|
| 1 | A password reset changed the password but **left every issued token working** | **FIXED** — every token carries a `tv` claim checked on every request; a reset bumps it |
| 2 | *(found by the tests)* `token/refresh/` kept serving a revoked user | **FIXED** — the refresh endpoint never goes through DRF's authentication classes, so it needed its own check |
| 3 | No remedy for "I think someone else is logged in as me" | **BUILT** — `POST /auth/logout-all/` |
| 4 | A signed-out visitor clicking `+` got *"Session expired. Please login again."* | **FIXED** — `ProductCard` routes to login and returns to the product afterwards |

### 1. Why not `token_blacklist`

The obvious answer is SimpleJWT's blacklist app. It is the wrong tool: it blacklists
**refresh** tokens, so the access token derived from a blacklisted one keeps working until its
own expiry. The threat here is precisely the outstanding access token, which lives for a day.

A version claim is checked on *every* request, which is the only thing that can end an access
token early without a server-side session store.

### 2. How it works

| Piece | Role |
|---|---|
| `UserProfile.token_version` | The counter. Bumping it invalidates everything issued before the bump, for that user only |
| `tv` claim | Stamped on every token at login, and carried onto derived access tokens |
| `VersionedJWTAuthentication` | The project's `DEFAULT_AUTHENTICATION_CLASSES`. Compares the claim on every request, 401 on mismatch |
| `VersionedTokenRefreshSerializer` | The same check at `token/refresh/` |
| `revoke_tokens(user)` | Bumps the version. Called by password reset and `logout-all` |

**Backwards compatible:** tokens minted before this existed carry no claim and read as version
0, which matches the default, so deploying it signs nobody out. Asserted by
`test_legacy_tokens_without_the_claim_still_work`.

### 3. The bug the tests caught

The first implementation only guarded `VersionedJWTAuthentication`. `test_password_reset_invalidates_the_refresh_token_too`
then failed with `200 != 401` — because **the refresh endpoint does not go through DRF's
authentication classes at all**. It validates the refresh token itself. So a revoked user's
refresh token was still accepted and still minted access tokens.

Those tokens would have been rejected on use, but the endpoint answering `200` is both
misleading and lets a holder keep trying. Fixed with `VersionedTokenRefreshSerializer`.

This is exactly the kind of hole a happy-path test misses: "the reset worked" was true, and the
session was still alive.

### 4. What a bump does *not* do

Stated plainly, because it would be easy to overclaim: bumping invalidates **tokens**. It does
not touch anything that never had one. A password hash changing does not by itself revoke
anything — `revoke_tokens()` has to be called. There is no server-side session table, so
"sign out all devices" means "invalidate all issued credentials", which is the same practical
outcome but worth being precise about.

### 5. Verifier hygiene fixed along the way

Running the sweep exposed two verifier bugs of my own, both of which made a working product
look broken:

- **Fixed probe usernames collided on a re-run.** `register` returned 400 "already exists" and
  the script silently skipped its most important section. Now unique per run
  (`verifyday4probe<hex>`), with `purge_verification_users` matching the `verifyday` prefix so
  they are still cleaned up.
- **The password-reset throttle (10/min per IP) is shared across verifiers.** Running the
  sweep back to back exhausted it, and `verify_day4` reported **10 failures that were all the
  same 429**. A rate limit doing its job is not a product bug. The reset section now detects
  the throttle once and reports a single clearly-labelled **SKIP** rather than ten false
  failures. Verified by running it twice in a row: `71 passed, 0 failed, 2 skipped` both times.

Both are the same lesson as the Day 3.4 test bugs: a verifier must assert what it established,
and must not blame the product for its own environment.

### Verification after Day 7

| Suite | Result |
|---|---|
| `manage.py test` | **257 pass** (was 236) — 21 new for ritual admin CRUD + item editing |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | 55/55 — no regression |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| `verify_day4.py` | 88/88 (needs ~1 min after another reset-heavy run — see above) |
| `verify_day6.py` | 40/40 — no regression |
| `verify_day7.py` | **30/30** |
| **Live assertions** | **450** |

Frontend builds clean. Database restored to seeded state after purging.

### Docs updated

`AGENTS.md` (§7 new "Token revocation" subsection, §13 the caveat replaced with the contract),
`API-SPEC.md` (both endpoints, the response wording, and the refresh-endpoint note),
`FEATURES.md` (the gap row removed), `README.md`, this file.

---

## Day 6 Completed (2026-09-19) — the missing entry point

**Theme:** `AGENTS.md` §1 requires discovery through six entry points. Five worked.
The sixth — **Puja** — did not exist in any form.

**Verification: 219 backend unit tests + 420 live assertions, all passing.**

| # | Was | Now |
|---|-----|-----|
| 1 | **The Puja entry point did not exist.** No model, no field, no endpoint, no page — the word appeared only in branding copy | **BUILT** — `Puja` + `PujaItem`, `/pujas` and `/pujas/<slug>`, 8 seeded rituals, nav + home + footer links |
| 2 | **`festival_type` conflated two different things** — calendar festivals (`dashain`, `tihar`, `shivaratri`) *and* rites of passage (`bratabandha`, `pasni`, `griha_pravesh`, `shraddha`). Two of its own labels end in "Puja" | **UNTANGLED** — `Puja` is the ritual, `FestivalKit` is one bundle that serves it |
| 3 | No way to buy what a ceremony needs **without** a kit | **BUILT** — `POST /orders/cart/add-puja/<id>/` adds the essentials, reports what it skipped |
| 4 | An unknown slug fell through to a bare default 404 | **FIXED** — styled app-wide `not-found.js`, and `notFound()` for an unknown ritual |
| 5 | *(found while building)* `const { slug } = params` — Next 16 makes `params` a **Promise** | **FIXED** — every valid ritual would have 404'd, and the build would not have caught it |

### 1. What was actually wrong

`festival_type` was doing double duty. Its seven used values were:

| Value | Actually is |
|---|---|
| `dashain`, `tihar`, `shivaratri` | Calendar festivals — arrive on a date |
| `bratabandha`, `pasni`, `griha_pravesh`, `shraddha` | **Rites of passage** — happen when a family needs them |

And the enum's own labels give the game away: `chhath` → "Chhath **Puja**",
`saraswati` → "Saraswati **Puja**". A ritual and a purchasable bundle are different
things, which is why the brief lists **Puja** and **Ready-made Kit** as separate
entry points.

### 2. The model

| Model | Purpose |
|---|---|
| `Puja` | name, slug (uniquified in `save()`), description, `occasion_type`, `is_active` |
| `PujaItem` | puja → product, `quantity`, `is_required`; `unique_together ('puja','product')` |
| `FestivalKit.puja` | nullable `SET_NULL` FK — which ritual this bundle serves |

`PujaItem` is **not** redundant with `KitItem`: a kit's optional extras are a
merchandising decision, a puja's list is the ritual requirement.

**A ritual can exist with no kit**, and 3 of the 8 seeded ones do — `Daily Puja` is
the clearest case. That is why Puja has to stand alone rather than being a view
over kits.

### 3. Seeded from the project's own assertions — nothing invented

`manage.py seed_pujas` (idempotent, non-destructive, `--check`):

- the seven kit-backed rituals take their samagri straight from the kit that
  already ships for them, keeping the same `is_required` split;
- `Daily Puja` takes the products the recommender's own `STAPLE_CATEGORIES` already
  designates as "everyday puja essential";
- each ritual's description is the existing **kit's** description, not new copy.

**It is a command, not a data migration, and that is deliberate.** Products,
categories and kits are created by `seed_data`, not by any migration. A migration
seeding puja items would find an empty catalogue on a fresh database and quietly
produce eight rituals with no samagri — it would look like it worked. `seed_data`
now calls `seed_pujas` last.

### 4. Frontend

Both pages are **Server Components**, like the home page. The data is entirely
public, so no token or client boundary is needed — which also makes the output
verifiable without a browser. Only the add-to-cart button is a client component
(`AddPujaButton`), because that is the only interactive part.

Verified from the server-rendered HTML:

```
/pujas/dashain-tika   →  Dashain Tika · Dashain · 6 essential · 2 optional
                         Sindoor Powder (Red) ×2  Rs. 100.00
                         Artificial Marigold Garland ×2  Rs. 400.00
                         Essentials only  6 items  Rs. 1080.00
                         Ready-made kit: Dashain Puja Complete Kit, 8 items, 10% off
/pujas/daily-puja     →  Essentials only, and NO kit panel  ✓
/pujas/unknown        →  the styled 404
```

An unknown slug returns **200** rather than 404: `notFound()` fires but the response
has already started streaming, so the status line is committed. This is Next's
documented behaviour and it injects `<meta name="robots" content="noindex">` as the
mitigation. The RSC payload carries `NEXT_HTTP_ERROR_FALLBACK;404`.

### 5. Two bugs found while building

**The Next 16 `params` Promise.** `const { slug } = params` yields `undefined`, so
every valid ritual would have been sent to `notFound()`. The build compiles it
happily — it is a runtime value, not a syntax error. Caught by checking
`node_modules/next/dist/docs/` rather than assuming, exactly as §2 of `AGENTS.md`
instructs. Now recorded there as a named trap.

**A verifier asserted a precondition it had not created.** `verify_day6.py` opened
with "cart starts empty" and failed — because it was not. The fix was to clear the
cart first. Same class of mistake as the Day 3.4 test bugs: assert what you
established, not what you hoped.

### Verification after Day 6

| Suite | Result |
|---|---|
| `manage.py test` | **219 pass** (was 185) — 24 for the entry point, 10 for add-puja |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | 55/55 — no regression |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| `verify_day4.py` | 88/88 — no regression |
| `verify_day6.py` | **40/40** |
| **Live assertions** | **420** |

Frontend builds clean, all puja routes in the compiled manifest, `no-undef` lint
clean. Database restored to seeded state after purging.

### Docs updated

`DATABASE-DESIGN.md` (`Puja`, `PujaItem`, `FestivalKit.puja`, why a command not a
migration), `API-SPEC.md` (both endpoints + `add-puja` with its skip reporting),
`FEATURES.md` (§1 rewritten with the six entry points), `AGENTS.md` (§1, §2 Next
traps, §3 app map + model facts, §5 commands, §12 counts), `README.md`, this file.

---

## Day 5 Completed (2026-09-19) — the festival domain, made visible

**Theme:** the project's differentiator was invisible on the first screen. The home
page led with a generic product grid, which is exactly the "generic shop with a
religious category bolted on" outcome `AGENTS.md` calls a failed project.

**Verification: 185 backend unit tests + 380 live assertions, all passing.**

| # | Was | Now |
|---|-----|-----|
| 1 | Home page opened with a generic product grid; the festival calendar was a small side section | **REBUILT** — leads with the next festival: name, countdown, description, its kit (or an honest "no kit yet"), and a **Required Samagri** panel |
| 2 | Three product cards had drifted apart. The home version omitted the unit and its "+" button **had no handler** — it looked like add-to-cart and did nothing | **ONE SHARED `ProductCard`** used by home, catalogue and recommendations, with working add-to-cart and an optional reason/urgency slot |
| 3 | Festival type filter was a hardcoded list of 7 types | **DERIVED from the kits that exist** — same trap as the old hardcoded `CITY_CHOICES` |
| 4 | `/festivals/upcoming/` was hardcoded to `[:5]`, so 5 of the 10 active festivals were unreachable | **`?limit=`** (default 5, max 50) |
| 5 | *(regression I introduced and caught)* The spotlight offered "Get this kit" for a festival that has no kit | **FIXED** — the spotlight's kit and the required-samagri panel are separate values |

### 1. The home page now leads with the domain

```
Hero (with "Ganesh Chaturthi · In 5 days")
  ↓
Next festival spotlight  →  countdown, description, kit box or honest "no kit yet"
  ↓  alongside  →  Required Samagri panel (only `is_required` items)
Recommended For You     →  4 cards, each carrying the backend's reason text
The Festival Calendar   →  4 festivals, soonest first
Featured Samagri
Why choose us           →  names the algorithm and whether ranking was personalised
```

Verified live: the hero badge reads `Ganesh Chaturthi · In 5 days`, and the
spotlight renders `We do not have a ready-made kit for Ganesh Chaturthi yet.`
with a link to the recommender — because **3 of the 6 soonest festivals have no
kit** (Ganesh Chaturthi, Haritalika Teej, Indra Jatra). Handling that case was not
hypothetical; it is the default state of the calendar today.

The `meta` block from the recommender is surfaced on the page
(`Ranked by weighted-signal-ranker over 21 candidates. Sign in to personalise…`),
so the ranking is not a black box.

### 2. Required samagri, and a design problem it exposed

`KitItem.is_required` is the Required Samagri mechanism — `AGENTS.md` says "use
it", and nothing in the UI showed it. The panel lists only required items with
prices and links to the kit.

The first implementation tied the panel to the next festival's kit, so on a
kitless festival the panel vanished — hiding the project's key domain concept
whenever the calendar happened not to cooperate. The panel now follows the
**nearest festival that has a kit** and names it
(`For Ghatasthapana (Dashain Begins) · In 32 days`), which is honest and always
populated.

### 3. One product card

`components/ProductCard.js` + `.module.css`. Client component, because the add
button needs the cart context; it reads the context itself rather than taking a
callback so the Server Component home page can render it without passing a
function across the boundary. Optional `reason` and `badge` props carry the
recommendation explanation and festival-urgency label.

The old card CSS was deleted from `page.module.css`, `products.module.css` and
`recommendations.module.css` rather than left as dead code.

### 4. Two hardcoded lists removed

- **Festival type filter.** Was 7 literal entries in `festivals/page.js`. Now
  derived from the kits' own `festival_type` / `festival_type_display`. Coverage is
  identical today, one label is better (`Pasni (Rice Feeding)` vs `Pasni`), and a
  kit for a new type can no longer exist without a way to reach it.
- **`/festivals/upcoming/` limit.** Was `[:5]`. Now a parameter — the calendar has
  10 active festivals and only 5 were reachable.

### Verification after Day 5

| Suite | Result |
|---|---|
| `manage.py test` | **185 pass** (was 178) — 7 new, covering the `limit` contract |
| `verify_day2.py` | 68/68 — no regression |
| `verify_day3.py` | 55/55 — no regression |
| `verify_day3b.py` | 41/41 — no regression |
| `verify_day3c.py` | 128/128 — no regression |
| `verify_day4.py` | 88/88 — no regression |
| **Live assertions** | **380** |

- Frontend builds clean, 13/13 routes. All 10 checked routes return 200, including
  `/festivals?type=dashain` (kit exists) and `/festivals?type=other` (no kit).
- `npx eslint --rule '{"no-undef":"error"}' src/` clean — no undefined identifiers
  in the new component.
- Database restored to seeded state after purging: 3 users · 35 products ·
  10 categories · 3 areas · 1 vendor · 8 orders · 0 cart lines · 8 status events ·
  7 kits · 10 active future festivals.

### Docs updated

`FEATURES.md` (three rows moved out of "not built", Day 5 fix list),
`API-SPEC.md` (`?limit=` contract with the full truth table), `UI-UX-SPEC.md`
(shared card, festival-first home), `AGENTS.md` (the two new rules),
`README.md`, this file.

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
- ~~Reviews and ratings (no `Review` model exists).~~ ✅ **BUILT Day 11** — model, endpoints,
  storefront section and `/reviews` moderation. See §Day 11.
- ~~Password reset.~~ ✅ **BUILT Day 4**, sessions revoked Day 7.
- Per-vendor and per-area analytics.
- ~~Personalized recommendations from purchase history.~~ ✅ **BUILT Day 2**.
- An image-upload widget — kits and products have an `image` column and no UI sets it.
- ~~Search relevance: `icontains` only, no fuzzy or typo tolerance.~~ ✅ **BUILT Day 12** —
  relevance-ranked, transliteration-aware, domain-aware. See §Day 12.

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
| 11 | Admin CRUD write actions (products, categories, areas, **kits, rituals + their items**) | ✅ **Done** — kits and rituals added Day 8 |
| 12 | Customer order tracking / status timeline | ✅ **Done** — 5-step timeline + distinct cancelled state |
| 13 | Responsive polish + four-state audit on every screen | ✅ **Done** — tables scroll & pin, sidebar is a drawer under 880px |
| 14 | Full demo rehearsal | ✅ **Done** — automated as `verify_day3c.py` (128 assertions) |
| 15 | Routed product detail endpoint (`/api/products/<slug>/`) | ✅ **Done** — was missing entirely |

### P1
| Item | Status |
|---|---|
| ~~Reviews and ratings~~ | ✅ **Done Day 11** — see §Day 11 |
| ~~Password reset (B9)~~ | ✅ **Done Day 4**, sessions revoked Day 7 |
| ~~Personalized recommendations from order history~~ | ✅ **Done Day 2** |
| Wishlist | ⬜ Open |
| Image upload widget (kits + products have the column, no UI) | ⬜ Open |
| Vendor / per-area analytics | ⬜ Open |
| ~~Search relevance — `icontains` only, no fuzzy matching~~ | ✅ **Done Day 12** — see §Day 12. Remaining limits listed honestly in `docs/SEARCH.md` §7 |

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
