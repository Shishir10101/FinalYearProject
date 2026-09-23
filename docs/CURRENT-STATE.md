# CURRENT-STATE.md

Analysis date: 2026-09-18
Method: full source inspection + live server probing.
Last updated: 2026-09-23 (**Day 16 complete** — the store is renamed **Puja Sewa**, every
product/category/kit now carries a real photo, and the landing page's scroll jank is fixed and
measured. Days 15c, 15b, 15, 14b, 14, 13.1 and earlier are complete.)

---

## Day 16 Completed (2026-09-23) — a rebrand, 52 real photos, and a landing page that scrolled badly

### 1. The broken images were one endpoint, not the media setup

The storefront's "Recommended For You" row rendered as broken-image icons. `media/` was
serving correctly the whole time — the first probe said `size 0`, which was the **`curl -o
/dev/null` exit-23 artifact**, and because that exit code broke an `&&` chain the settings
grep never ran and `MEDIA_URL` looked missing. It is not.

The real cause: **`/api/festivals/recommendations/` was the only endpoint returning *relative*
image URLs** (`/media/products/x.png`). Every other endpoint returned absolute ones. The
storefront resolved the relative form against its own origin on `:3000` and 404'd.

Root cause was in `festivals/recommender.py`: `serialize_recommendations()` built the
serializer as `serializer_class(entry.product)` with **no `context={'request': request}`**.
A DRF `ImageField` needs the request to call `build_absolute_uri()`; without it, it silently
falls back to the relative path. Generic views pass context automatically — this helper is
called by hand, so it had to be threaded through explicitly. **A serializer built by hand is a
serializer missing its context.**

### 2. Real imagery — `manage.py fetch_demo_images` (new)

Before: **5 image files** for 35 products (one generic placeholder reused across most of
them), **all ten categories with no image at all**, and every file was JPEG data behind a
`.png` extension. Now 52 relevant photos, 600×600 JPEG q82, with per-file attribution in
`media/IMAGE-CREDITS.md` (Commons images are CC/PD and require it).

Two things this cost, both worth keeping:

- **Commons returns `429` and the API helper swallowed it**, so a throttled row was
  indistinguishable from "nothing found" and silently became a fallback tile. Two runs of the
  *same code* produced *different* fallback lists — that was the tell. Now it retries with
  exponential backoff, honouring `Retry-After`.
- **A wrong photo is worse than a drawn tile.** Keyword matching cannot see a near-miss, and
  Commons is full of them: *conch fritters* for "conch shell", *coconut cookies* for "dried
  coconut", an *incense-making machine* for "chandan agarbatti", a *chemical condensation
  diagram* for "benzoin resin", a *balloon* for "kalash", and a **portrait of the writer
  Jaishankar Prasad** for "prasad". All are now rejected by keyword. One row of 52 (Hawan
  Samagri Mix) remains a drawn tile, which is honest rather than wrong.

The quality check that actually worked was **looking at the images**: a labelled contact sheet
rendered with Pillow and read back as an image (`docs/_evidence/2026-09-23-demo-imagery-contact-sheet.jpg`).
No assertion would have flagged a cookie standing in for a coconut.

### 3. The landing-page scroll jank had four real causes

1. **`backdrop-filter: blur(12px)` on the `position: sticky` navbar** — the compositor re-blurs
   everything scrolling beneath a full-width 70 px bar on every frame. Replaced with an opaque
   `var(--bg-primary)`, visually identical at 92 % alpha over a cream page.
2. **`animation: pulse 2s infinite` on the navbar logo** — an infinite transform inside an
   always-visible sticky element keeps it repainting forever, for a decoration nobody reads as
   motion.
3. **Two 400 px rotating circles with `border: 2px dashed` in the hero** — a dashed border on a
   circle is expensive to rasterize and, unpromoted, was re-rasterized every frame. The design
   is kept; `will-change: transform` lifts each onto its own layer.
4. **~7 MB of eager image decode** — 11 cards × ~700 KB originals. Now `loading="lazy"` +
   `decoding="async"`, and the new images are 40–70 KB each.

No scroll listeners and no request loops were involved. The "only after login" impression was a
red herring — the cost was always present; logging in simply made the page long enough to
scroll.

**The check that keeps it honest:** `frontend/scripts/scroll_probe.mjs` scrolls the page in a
real browser and counts frames over 50 ms. Nothing else in the project could see this — the
unit tests do not render, `storefront_check.mjs` asserts content rather than smoothness, and the
build passes either way.

### 4. Rebrand: the store is now **Puja Sewa**

The judgement call worth recording: **the store's name changed; the merchandise category did
not.** "puja samagri" is what the shop sells — and it is also one of the six required discovery
entry points — so it stays wherever it means the goods. `AGENTS.md` §1 now says so explicitly.

Renamed: navbar logo, footer brand and copyright, `<title>`, hero H1, the password-reset email
subject *and* body, `DEFAULT_FROM_EMAIL`, the `seed_data` help text, the banner in the six
tracked analysis scripts, `README.md`, `RUN.md`, `AGENTS.md` §1.

Deliberately **not** renamed: `admin@pujasmagri.com` (a seeded account identifier that matches
the live database and `docs/API-SPEC.md` — renaming would desync seed from data),
`vendor@pujasmagri.com` (inside a migration, which is history and must not be edited), and the
generic merchandise uses in metadata, docstrings and `docs/FEATURES.md` §1. The metadata
description and keywords keep "puja samagri" on purpose: search traffic arrives on the goods,
not on the brand.

### Verification
`manage.py test` → **498 tests, OK**. `storefront_check.mjs` → **136 passed, 0 failed** against
a production build. Scroll probe → **0 long frames of 354, worst 22 ms**, 12 images, 0 broken,
0 relative. All 52 images serve 200 with real bytes. The old brand name appears **0 times** on
all seven storefront routes. The reset email was triggered live and read out of the console
backend, confirming the rebrand reached the email as well as the screen. Harness leftovers
purged (17 orders across the session); stock re-checked at **0 of 35 products drifted**.

Two traps hit along the way, both now in `AGENTS.md`:
- **A matching PID is not proof of a stale server.** Windows reuses PIDs, so the replacement
  process inherited the killed dev server's number. Verify *identity* with the build ID
  (`cat .next/BUILD_ID`, grep the served HTML), never the PID.
- **Never pipe a build into `head`.** `npm run build | tee log | head -14` SIGPIPEs the build
  once `head` is satisfied, leaving `.next` half-written. It still prints `✓ Compiled
  successfully`, then `next start` says `✓ Ready` and dies with `Unexpected end of JSON input`.
  Redirect to a file and read it; confirm with a JSON sweep of `.next/**/*.json`.

---

## Day 15c Completed (2026-09-22) — the last endpoint nobody called, and a check that failed for a reason it never named

**Theme:** Day 15 and Day 15b both ended the same way — *grep for an endpoint that exists but
nothing invokes*. This is that sweep finished, and then the fallout of running it.

### The finding

`/api/analytics/inventory/` was fully built, correctly vendor-scoped through `scoped_products`,
routed in `analytics/urls.py`, and documented — with **no unit test, no live assertion and no
client calling it.** It was the one analytics endpoint with zero coverage of any kind.

The trap in writing its tests is worth recording. The seeded catalogue's **minimum stock is 25
units** and the endpoint's threshold is **10**, so on demo data *every count is legitimately
zero*. A test written against seed data would have passed no matter what the thresholds did —
a check that passes for the wrong reason. `InventoryAnalyticsTests` therefore sets stock
explicitly on its own fixtures.

### The contract the tests pinned, after I got it wrong twice

`stock__lt=10` **includes `stock=0`**, so **`low_stock_products` and `out_of_stock_products`
are nested, not disjoint** — every out-of-stock product also appears in the low list. That is
correct behaviour, but it is a trap for any screen rendering both lists, because the
out-of-stock rows would be shown twice.

My first two attempts asserted `low_stock_count == 2` (it is **3** — I had forgotten `Inv Out`
counts as low) and a vendor `total_products == 3` (it is **4** — `Inv Exactly Ten`, stock 10,
is active). The failures, not the reading, produced the real contract.
`test_out_of_stock_is_a_subset_of_low_stock` now pins it explicitly.

### The fix

A **Stock Health** panel on the dashboard home, from a fifth `Promise.all` fetch. Its empty
state is load-bearing rather than decorative: because the seeded catalogue can never reach the
threshold, the empty state is what the shipped demo actually shows, and an unexplained blank
panel reads as "broken". It states the threshold and the subset relationship in words.

The low-stock branch was proven with a scratch product (`ZZ E2E Low Stock Probe`, stock 3),
observed rendering one row and `Low (3)`, then deleted — seeded data untouched, per the
standing decision.

### The harness failure that was not a regression

After the purge, the dashboard harness failed **`the three seeded delivery areas are still
listed` — on 2 of 3 consecutive runs**, with one run crashing outright and printing no summary
at all. The database had all three areas and a clean 3/10 area/category split throughout.

I had seen this exact failure earlier and explained it away as *"two harnesses running
concurrently"*. **That explanation was wrong**, and repeating it would have buried a real bug.
It reproduces with a single process.

The actual cause: deleting the scratch row calls `load()`, which sets `loading = true`, and
`AreasPanel` renders three `.skeleton-line` divs **instead of the table** while that is true
(`settings/page.js:375`). The harness's `waitForFunction` only waits for the scratch *name* to
disappear — which happens the instant the skeletons mount, **before the refetch returns** — and
the next line then read `body.innerText()` against an empty panel.

Measured at that exact instant: `skeletonCount: 3, tableRowCount: 0, hasTable: false,
seesKathmandu: false`. After waiting for a row: `tableRowCount: 3`, all three names present.

So the assertion **never tested the data.** It raced a loading state that is indistinguishable
from "no rows" by `innerText` alone.

Three changes, all the same lesson — *wait on the thing the assertion is about*:

1. The seeded-areas check now waits for `.table tbody tr` before reading, and an added
   `the areas table is populated, not merely name-free` distinguishes "zero rows" from
   "not rendered yet". The original check could not tell those apart.
2. The Areas tab-switch replaced a bare `waitForTimeout(1500)` with the same row wait — the
   identical race, one assertion earlier, still latent.
3. The Categories row wait is now `.catch(() => {})`-guarded, because an unguarded
   `waitForSelector` timeout throws out of `main()` and takes the whole run with it. That is
   what the silent third run was.

### Verification

- **498 unit tests** (489 + **9** `InventoryAnalyticsTests`), `OK`
- Dashboard browser **112 → 119**, and **119 / 0 failed on three consecutive runs** — the
  previously 2-of-3 flaky check now passes deterministically
- Storefront browser **136 / 0 failed**
- Baseline drift-checked exact after every sweep: **35 products / 4725 stock / 2380 popularity
  / 8 orders / 3 users / 3 areas / 10 categories**, zero scratch residue
- The purge earned its keep: the harness runs placed 7 orders, and `purge_verification_orders`
  returned exactly 7 units and reversed exactly 7 popularity points

---

## Day 15b Completed (2026-09-22) — two capabilities the product could not reach

**Theme:** the same question as Day 15, asked of the account endpoints instead of the
analytics ones — *which endpoint does no client call?*

### The finding

An audit of every `accounts` route against storefront references returned this:

| Endpoint | Backend | Storefront refs |
|---|---|---|
| `/auth/register/` | built | 2 |
| `/auth/login/` | built | 15 |
| `/auth/token/refresh/` | built | 1 |
| `/auth/profile/` | built | 2 |
| `/auth/password-reset/` | built | 2 |
| `/auth/password-reset/confirm/` | built | 1 |
| **`/auth/logout-all/`** | **built, tested, documented** | **0** |
| **change password** | **did not exist at all** | — |

`LogoutAllView` has existed since Day 7, has its own docstring calling it *"a real
user-facing action rather than an internal one"*, appears in `verify_day7.py` and in
`docs/API-SPEC.md` — and **no UI anywhere called it.** The project documented a security
feature that a customer could not invoke.

Separately, the only way to change a password was the **forgot-password** flow, which needs
mailbox access and asks you to assert you have *lost* the password. A signed-in customer who
simply wanted a different one had no screen and no endpoint.

### The fix

**`POST /api/auth/password-change/`** plus an **Account Security** panel on `/account`
carrying both this and "Sign out everywhere".

`PasswordChangeSerializer` deliberately **requires the current password**, and that is the
whole security argument rather than a formality: the caller is already authenticated, so
without it any stolen access token could be escalated into permanent account takeover — the
thief changes the password and locks the owner out. This makes it *stricter* than the reset
flow, which is correct rather than inconsistent: possessing an emailed reset link is itself
proof of mailbox control, so the two are not equivalent.

The change **revokes every token including the caller's own**, matching
`PasswordResetConfirmView`. Still justifiable: leaving the old tokens alive would mean the
change protected nothing already stolen, which is the usual reason to make it.

### Verified live, every branch

| Case | Result |
|---|---|
| anonymous | `401` |
| wrong `current_password` | `400` — **and the old password still works afterwards** |
| `new_password` == current | `400`, not a silent no-op reported as success |
| `new_password` weak | `400` — Django's validators fire |
| mismatch | `400` |
| success | `200`, `reauthentication_required: true` |
| the token that made the change | **`401` afterwards** |
| old password | `401` · new password `200` |
| `logout-all` | `200`, `token_version = 2`, token dead after |

The test that gives the 400s meaning is `test_wrong_current_password_changes_nothing`: a 400
that still wrote the password would satisfy "it returned 400" perfectly.

### A harness bug, of the kind this project keeps producing

The new browser section failed on three assertions and a 30-second locator timeout — **none
of which had anything to do with the panel.** The reset section above it deliberately clears
`localStorage` to prove a spent link is refused while signed out, so the probe account was
not signed in and `/account` legitimately rendered its "Please login" branch. The section now
signs the probe account in explicitly and asserts that sign-in first: **own the precondition
you assert.**

### Verification

- **489 unit tests** (was 477; **+12** — `PasswordChangeTests` 9, `LogoutAllTests` 3)
- Browser: storefront **124 → 136** (+12 — the whole Account Security panel, driven not just rendered)
- `curl`-level check of all nine branches above, against the running server
- Panel screenshot confirms it renders in the app's own design language, not just that the
  selectors match

---

## Day 13.1 Completed (2026-09-22) — inventory that was leaking, and a seed that lied

**Theme:** after closing every P1 item, an audit of the parts nobody had looked at turned up
two defects that were **invisible by construction** — neither could be seen from the code,
the tests, the builds or the browser checks, because both only manifest as *accumulated
drift* over many runs.

### 1. Cancelling an order never returned its stock

`CheckoutView` decrements `product.stock` for every line. `AdminOrderUpdateView` wrote a
status-history row and nothing else — so **cancelling an order leaked its inventory
permanently.** The goods are back on the shelf, the system still counts them as gone.

Reproduced before fixing: order 2 units (24 → 22), cancel, stock stays 22.

Then measured. Comparing every product against the values in `seed_data.py`:

```
  Dashain Tika Set                150     24   -126
  Cotton Wicks (Batti) - 100pcs   500    478    -22
  ...23 products in total
  net units lost from inventory: 538
```

That is not cosmetic. It produces **false low-stock and restock alerts**, so the demand-
prediction feature — one of the two AI components the brief requires — was reporting on
inventory that does not exist.

**Two leaks, not one.** `purge_verification_orders` deleted the orders a sweep created and
also never released their stock, so *every verification run* shrank the catalogue. The 538
units came mostly from that, not from cancellations.

**And a second field went with it.** Checkout increments `popularity_score` as well, and
nothing reversed that either: measured at **591 points across 23 products**, with `Dashain
Tika Set` at 256 against a seeded 98. That is not just a display artefact — the field feeds
the **recommendation engine's popularity bonus** (`festivals/recommender.py`), the trending
list, the default catalogue ordering and the search tie-break. Left alone, the demo was
recommending whatever the test suite happened to buy.

| Fix | Where |
|---|---|
| `release_order_stock()` / `reserve_order_stock()` / `reverse_order_popularity()` | `orders/views.py` |
| Cancel restores stock; un-cancel re-reserves; a reinstatement with no stock is **refused** (400) | `AdminOrderUpdateView.perform_update`, atomic |
| Purge releases stock (not for already-cancelled orders) and reverses popularity (for all of them) | `purge_verification_orders` |
| `seed_data --reset-stock` / `--reset-kit-items` / `--reset-popularity` — the repair paths | `products/management/commands/seed_data.py` |

**`popularity_score` is deliberately not reversed on cancellation**, and *is* reversed by the
purge. The distinction is not "cancel or not" but **real or fixture**: a cancelled order still
means a customer asked for something, whereas a verification order means nobody did. `stock`
is a factual count of what is on the shelf and must be exact; `popularity_score` is a demand
signal and is allowed to be monotonic over real traffic.

### 2. `seed_data` existed twice, and the documented one never ran

`AGENTS.md` said: *"`seed_data` exists twice … Only `core`'s runs. If you change seeding,
change `core`'s; delete the other."* **That was backwards.**

`core/` is the Django *project* package — `settings.py`, `urls.py` and `wsgi.py` live there —
and it is **not in `INSTALLED_APPS`**. Django only discovers management commands from
installed apps, so `core`'s copy was dead code that had never run, while the file the docs
told you to edit had no effect. The live copy (`products`') had silently drifted: it never
called `seed_pujas`.

Measured on a genuinely fresh database:

```
  products             35
  kits                  7
  rituals (Puja)        0  <-- EMPTY
```

**The Puja entry point — one of the six `AGENTS.md` §1 requires — did not exist on a fresh
install.** It was present here only because somebody had run `seed_pujas` by hand once. The
dead copy is deleted, the live one is complete, and `SeedDataCompletenessTests` asserts that a
plain `seed_data` produces every entry point.

### 3. A kit had lost its own headline item

`seed_data` writes kit items only `if created`, so a line removed from a seeded kit is
**unrecoverable by re-seeding**. "Dashain Tika Set" was missing from the *Dashain Puja
Complete Kit* — 8 items instead of 9, one required count short, and `total_price` understated
by Rs. 180. Repaired, and `--reset-kit-items` added (re-adds missing lines, corrects drifted
quantities, **never deletes** a line an admin added by hand).

### 4. `/orders` had no browser coverage, and it needed some

`/orders`, `/forecast` and `/settings` were the three dashboard screens the browser check
never visited. Auditing `/orders` turned up a defect the whole suite had missed:

**A failed status write was rendered as a failed load.** `updateStatus` set the same `error`
state the load path uses, and the render branch for that state replaces the entire table:

```
{loading ? skeletons : error ? "Could not load orders" : table}
```

So one rejected PATCH — a transient blip, or a rule the server enforces — blanked the order
list the admin was working through, under a heading that was simply untrue. The list had
loaded perfectly well.

Fixed by separating the two: `loadError` (fatal, may replace the screen) versus a
self-clearing `notice` with a kind (a write outcome, table preserved) — the pattern the
products screen already used. The same change made the post-write refresh **silent**, so
updating one "Last change" cell no longer dropped the whole table to skeletons.

**Nine new browser assertions**, including a regression guard that forces a real refusal: the
check intercepts the PATCH with Playwright's route API and returns a `400`, then asserts that
an error notice appears **and the table is still there**. That is the assertion the old
behaviour would fail, and it is deterministic rather than waiting for a real failure to occur.

> Writing that check found two bugs in the check itself, both worth recording. It asserted on
> the phrase "not allowed right now" — a string the API client never produces, because it only
> lifts `detail` / `error` / `non_field_errors` from a DRF body and falls back to its generic
> message for a per-field error. And it asserted the table survived a *successful* change
> immediately afterwards, which is precisely where the skeleton-blanking showed up. Assert on
> the element's state, not on prose you assume the client emits.

### 5. An interrupted sweep left a scratch area that looked like real data

Chasing the final verification turned up two operational facts, both now in `AGENTS.md` §12:

- **A twelve-verifier sweep does not survive in one burst here.** Partway through, the API
  process is still listening and still logging, but requests return `000` / `503` and then
  nothing. It is the sandboxed shell's HTTP layer saturating, not Django — the process is
  healthy and a restart clears it. Two batches (five verifiers, restart, seven verifiers)
  complete reliably, and both did: **796 assertions, 0 failures.**
- **`verify_day3b` named its scratch area `Kirtipur`.** A real place name, with no marker, so
  when a wedged server killed the run partway through, the leftover row was indistinguishable
  from legitimate data and made `verify_day3b` *and* `verify_day3c` fail on "only the three
  seeded areas remain" — two verifiers reporting a regression that did not exist.
  `verify_day3c` already did this correctly with `ZZ E2E Test Area` and a pre-clean; both now
  follow that convention. **Name scratch data so it announces itself, and pre-clean it** — a
  run can be interrupted at any point.

> The lesson generalises past this project: a verification suite whose scratch data is not
> self-identifying cannot distinguish "the feature regressed" from "the last run was killed".
> That is the same failure mode as a check that passes for the wrong reason, in reverse.

### 6. `/forecast` and `/settings` — and the bug the second one exposed

Adding the missing coverage to the last two screens found one more defect, on the screen
whose whole job is authoring the catalogue.

**Creating a category from the dashboard never worked.** The button was
`onClick={c.save}`, and `save(override)` treats its first argument as the payload — so React
handed it the **click event**, `JSON.stringify` ran on a synthetic event, threw on its
circular structure, and the request never left the browser. The dialog sat open with a
"Converting circular structure to JSON" message and the admin had no way to add a category.

What kept it hidden for the life of the project:

- **The other tab worked.** Delivery Areas calls a local wrapper that builds its payload
  explicitly, so only one of the two panels was affected — and a screen that half-works looks
  like it works.
- **The API path is fine**, and is covered: `verify_day3b.py` creates categories over HTTP and
  passes. The bug was purely in the button.
- **No browser check had ever visited `/settings`.** The defect was invisible to the build, to
  ESLint, to 471 unit tests and to every live API assertion.

Fixed at the call site (`onClick={() => c.save()}`) **and** in the handler, which now rejects
anything carrying `nativeEvent` — a React event always has one, a payload never does — so the
mistake cannot silently recur on either panel.

### Coverage added for the last two screens

| Screen | Assertions |
|---|---|
| `/forecast` | 8 — heading, model + version, restock rows, MAPE per row, the **horizon selector actually refetching**, the per-row "Why?" explanation, and the **synthetic-provenance banner** |
| `/settings` | 9 — both tabs, both tables, and a full **create → assert → delete** round trip on categories *and* delivery areas, plus "the three seeded areas are still listed" |

The forecast banner is the assertion worth keeping: the model is fitted on **generated** data,
and the project's rule is that it must never read as real demand. The API already carries
`is_synthetic` and a provenance note, and the UI renders it — but only a browser can prove the
banner is on the screen. A regression there would leave plausible-looking numbers reading as
measured demand, which is the single most misleading thing this demo could do.

### Verification

- **471 unit tests**: all green
- Browser: storefront **118**, dashboard **103** — see Day 14 below for the five routes that
  were uncovered at this point
- **A sweep now nets to zero.** After a full 12-verifier run plus both browser checks, both
  purges left *no* stock drift and *no* popularity drift — `seed_data --reset-*` reported
  nothing to repair. That is the check that the reversal paths are complete rather than
  merely present.
- Every product's stock matches `seed_data.py`; 89 ritual items; the Dashain kit has 9
- All 8 seeded orders and 3 real accounts intact

> **A note on how these were found.** Not by reading code — both were found by *comparing two
> things that should agree*: two dashboard panels (the Day 13 double-count), and the live
> catalogue against the seed source (this one). The second comparison is now a habit worth
> keeping: after a verification sweep, ask what the sweep moved and whether anything puts it
> back. `git status`, `media/`, and the seeded numbers are all part of that answer.

---

## Day 14 Completed (2026-09-22) — the five storefront routes nobody had ever loaded

**Theme:** Day 13.1 closed with a named task — the storefront had browser coverage on 85
checks but had **never visited five of its routes**. This closes them, and the headline is
that the task was correctly scoped: it found a real defect, plus a piece of documentation
that was making a false claim about the app's own behaviour.

### 1. `notFound()` on `/pujas/[slug]` returns HTTP 200, and two comments said 404

The most interesting finding, because the code was *right* and the documentation was *wrong*.

`src/app/not-found.js` carried this:

> `PujaDetailPage` calls `notFound()` for an unknown ritual slug, **which returns a real HTTP
> 404** — better than a 200 carrying a "not found" message inside it.

Measured with curl:

```
$ curl -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/pujas/zz-no-such-ritual-12345
200
```

**It returns 200.** The cause is `src/app/pujas/loading.js`: a `loading.js` opens a Suspense
boundary, so the response has begun streaming before the Server Component's `fetch` resolves.
`notFound()` then renders the 404 UI into an already-committed 200. This is precisely the
constraint `AGENTS.md` documents, and Next injects `<meta name="robots" content="noindex">`
as the mitigation — verified present on the response.

So the behaviour is correct, understood, and unfixable without giving up the loading skeleton
that makes the ritual pages feel fast. **What was wrong was the claim.** A future session
reading that comment would have assumed a status-code guarantee that does not exist, and
would have been entitled to "fix" a real bug into a fake one. Both comments (in
`not-found.js` and in `pujas/[slug]/page.js`) now state what actually happens, with the
measurement that establishes it.

This is the same failure mode the Day 13 `count == 12` note describes: **a check that passes
for the wrong reason is worse than no check.** Here it was a *comment* that was confidently
wrong, which is the same hazard with a longer fuse.

### 2. The five routes, and what each now proves

| Route | Assertions | The one that matters |
|---|---|---|
| `/pujas/[slug]` | 6 | loaded **by URL, not by click** — a client-side nav updates the URL before the Server Component payload renders, so only a direct load exercises `await params` |
| `/account/orders/[id]` | 4 | loaded by **reload**, so the timeline is fetched by the route rather than inherited from the checkout response |
| `/auth/register` | 5 | client-side refusal → valid submit → **lands signed in** |
| `/auth/forgot-password` | 5 | the generic notice **does not leak whether the address exists** |
| `/auth/reset-password` | 12 | the new password **actually signs in**, and the old one does not |

Storefront coverage: **85 → 118 assertions.**

### Why "by URL, not by click" is the assertion worth keeping

Everything on `/pujas/[slug]` was previously reached by *clicking a link from `/pujas`*. That
hides the single most dangerous trap in this Next version: `params` is a **Promise**, so
`const { slug } = params` yields `undefined` and every valid ritual would `notFound()`. The
build catches nothing — the mistake is a runtime value, not a syntax error.

The existing check did exercise the page, so it looked covered. It was not: a click through
client-side navigation can carry the slug in the RSC payload in a way a cold load does not.
The new check loads the URL directly and asserts the **ritual's own title** renders.

The reset flow is asserted the same way — the only thing that distinguishes "the form said
Saved" from "the password changed" is logging in with the new password afterwards, which the
harness now does, in the same browser session that owns the token.

### Verifier bugs found and fixed in the harness itself

Four checks failed on the first run. **None was an app bug** — all four were the harness
being wrong, which is worth recording because the instinct is to assume the opposite:

1. **A locator read after navigating away.** `hasResetLink` was computed on the
   forgot-password page, then the run navigated to `/auth/reset-password` and only *then*
   read the link's `href`. The link was gone; `getAttribute` timed out. Fixed by reading the
   href while the notice is still on screen.
2. **Asserting a behaviour the app never claimed.** The reused-link check expected
   `/auth/reset-password` to *reject* a spent token on load. The page renders the form
   optimistically — it cannot know the token is spent until it asks the API, and it only asks
   on submit. Rewritten to submit and assert the refusal, which is a stronger check than the
   original: it proves the server really refuses, and that the form is then withdrawn.
3. **A regex that did not match the app's copy.** `/not\s*found|404/` against a page whose
   heading is "We could not find that page". The assertion was correct in intent and wrong in
   text.
4. **An allowlist that missed the raw network lines.** Playwright reports non-2xx both as the
   API client's parsed error *and* as a bare `Failed to load resource: status of 400` line.
   Only the first was allowed through, so the guard failed on deliberate traffic.

The deliberate 4xx traffic the new sections generate (bad password, mismatched confirmation)
is allowlisted **by exact message**, not by status code. A blanket "ignore 400" would hide the
next genuine failure — see the Day 13 note on checks passing for the wrong reason.

### Verifier hygiene

The throwaway account is named `verifydaybrowser<stamp>` — self-announcing, unique per run, and
matched by the existing `purge_verification_users` prefix. The harness **runs that sweep
itself** at the end of the pass and asserts the account is gone, so the cleanup cannot be
silently skipped; the footer still names the command for a killed run. This follows the
`ZZ E2E …` convention established on Day 3.

Confirmed after six consecutive full runs:

| | seed declares | live |
|---|---|---|
| products | 35 | 35 |
| total stock | 4725 | 4725 |
| total popularity | 2380 | 2380 |

**Exact agreement, no drift.** 3 users, 8 seeded orders, 0 carts, 0 stray reviews, 0 wishlist
rows; `media/` untouched.

### Verification

- **471 unit tests**, all green
- Browser: storefront **118** (was 85), dashboard 103
- Purges net to zero across six consecutive runs
- No new dependencies, no stack change

---

## Day 14b Completed (2026-09-22) — the mocked gateways now admit it

**Theme:** with every P0 closed, the remaining risk the project's own register named was
P2: *"Live eSewa/Khalti integration (the current mock marks them paid unconditionally —
fine for a demo, **must be labelled as mocked**)."* It was not labelled. This labels it.

### The defect

`POST /orders/checkout/` handled an `esewa`/`khalti` order by setting
`payment_status = 'paid'` and `status = 'confirmed'` **with no gateway involved** — no
redirect, no signature check, no callback. A reasonable demo shortcut.

What was not reasonable: **nothing anywhere said so.** The checkout screen offered eSewa
and Khalti as ordinary choices and the order detail then rendered a green **paid** badge.
A customer could reasonably conclude money had changed hands. The code comment said
`# Mock payment` — visible to a developer, invisible to the person the screen was for.

This is the same rule the project already applies to the demand forecast, where synthetic
data is banner-labelled and `SyntheticSalesRecord` is a separate table so fabricated rows
can never be mistaken for real ones. **A mocked gateway deserves the honesty given to
fabricated sales.** Same class of defect as a number presented as measured when it is
generated.

### The fix: one constant, read everywhere

```python
# orders/models.py
PAYMENT_METHODS_ARE_MOCKED = {'cod': False, 'esewa': True, 'khalti': True}
```

Nothing downstream restates this. `OrderSerializer.payment_is_mocked` derives from it per
order; `GET /orders/config/` publishes `payment_methods[].is_mocked` for the form.
Flipping a value when a real integration lands removes every label at once — the only way
a disclosure like this stays true over time instead of rotting into a lie.

| Surface | What it now says |
|---|---|
| Checkout, **before** the choice | *"Demo build — no real payment is taken"* |
| Each simulated tile | A `Simulated` tag **on the tile**, not only in the banner above it |
| Order detail | *"'paid' above is simulated — eSewa was not contacted and no money changed hands."* |
| Status history | *"eSewa payment simulated — no gateway was contacted and no money was taken."* |
| **`cod`** | **Nothing** — cash genuinely is collected on delivery |

### The row that matters most

`cod` is deliberately **not** labelled, and that is asserted in both the unit tests and the
browser check. A disclosure applied to everything is not a disclosure — it teaches the
reader to ignore it. Getting this wrong in the *safe* direction is still wrong, which is
why the test suite pins both halves rather than only the one that protects the customer.

### Three verifier bugs found on the way

Recorded because each is a repeat of a known trap:

1. **A check that never ran and never said so.** `verify_day14.py`'s first draft called
   `request('GET', f'/api/orders/{id}/')` **without the token**. The endpoint is
   authenticated, so it returned 401, and the `if status == 200:` guard silently skipped
   **four assertions** — no FAIL, no SKIP, no output. The section looked like it had
   passed. Now the read is *asserted* rather than guarded, so a regression fails loudly.
2. **A restart that bound alongside the old server.** Two processes ended up LISTENING on
   :8000 at once and the **stale one won every request**, so a correctly written new field
   appeared never to have been added. `--noreload` means the old process never dies.
   `netstat -ano | grep :8000` must show no `LISTENING` row — `TIME_WAIT` is fine.
3. **A fixture added with no purge path.** The `verify_day14_disclosure.py` marker was
   missing from `purge_verification_orders.MARKERS`, so its orders survived the sweep.
   Caught by *running the purge* rather than assuming it covered the new file. Now added.

### Verification

- **477 unit tests** (was 471; +6 in `MockedPaymentDisclosureTests`)
- `verify_day14.py` — **21 live assertions**, new
- Browser: storefront **124** (was 118; +7 assertions across checkout and confirmation)
- Total live assertions **817**
- After the full sweep: seed and live agree exactly — 35 products, 4725 stock,
  2380 popularity, 8 seeded orders, 3 accounts, 0 carts. **No drift.**


### Resume with

```bash
cd backend && ./venv/Scripts/python.exe manage.py test        # 477 tests, all green
./venv/Scripts/python.exe manage.py seed_data --reset-stock --reset-kit-items --reset-popularity
./venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
./venv/Scripts/python.exe verify_day13.py                     # 68 assertions
./venv/Scripts/python.exe verify_day14.py                     # 21 assertions
```

---

## Day 15 Completed (2026-09-22) — a dashboard that lied to the one role nobody tested

**Theme:** with every P1 item closed, the question was not "what is next" but "which page
has never been loaded by *which role*". Three earlier defects in this project — the dead
"create a category" button, the invisible `/orders` failure replacement, the mocked
gateways — were all found by coverage *gaps*, not by reading code. This was the last one.

### The defect

`/analytics/sales/` and `/analytics/areas/` have both returned a `scope` field
(`'all' | 'vendor'`) since Day 9. **No client code ever read it.** Grepping the whole
dashboard for `scope` returned two hits, and both were comments.

So both audiences got the same page, the same panels, and different numbers — with nothing
on screen saying which. Measured on the seeded data:

| | `scope` | Total Revenue | Orders | Products |
|---|---|---|---|---|
| `admin` | `all` | **Rs. 6,760** | 8 | 35 |
| `vendor1` | `vendor` | **Rs. 1,810** | 3 | 12 |

The Total Revenue card's caption was the literal string **`All time`**, hardcoded, for every
role. A vendor was therefore told that Rs. 1,810 was their all-time revenue for the whole
shop, when the shop-wide figure was Rs. 6,760 — and 1,810 is 27% of it. **The API was
correct the entire time. The screen was the thing that lied**, which is precisely the class
of defect no API verifier can see.

### Why nothing had caught it

The vendor section of `browser_check.mjs` was genuinely thorough — login, scoped product
list (12 of 35), every row owned by the same shop, a locked vendor field. But it made
`/reviews` its **last** page for the vendor (deliberately, so nothing downstream depended on
navigating back to a scoped list) and **never visited `/`**. The dashboard home is the only
page whose numbers change meaning by role, and it had never been rendered as a vendor by any
check in this project.

### The fix

Scope is now **read from the response**, never inferred from the cached role — if the two
ever disagree the panel must describe what it actually fetched:

```js
const scope = data?.scope || areaData?.scope || null;
const isVendorScope = scope === 'vendor';
```

A banner (`data-testid="analytics-scope"`, `data-scope={scope}`) states outright whose
figures are on screen; the captions, the "Orders by Status" heading and the areas note all
follow the same flag. The admin sees "Shop-wide" and the plain "All time"; a vendor sees
"Vendor scope", **"Your products, all time"**, and "your products" tags. The banner renders
only when `scope` is present, so an older API build degrades to the previous behaviour
rather than inventing a claim.

### The assertion that keeps it honest

A scope banner over a figure identical to the admin's would be pure decoration. The harness
now reads **both** roles' Total Revenue and asserts they differ, and that the vendor's is the
smaller — 1,810 vs 6,760.

Two internal consistency claims were re-checked under vendor scope as well: the area rows
still sum to their own headline (1,810), which is the invariant `AreaBreakdownView` was built
to guarantee.

### A false finding I produced, and corrected

Nominated at the start of this session: *"there is no vendor analytics — `analytics/urls.py`
has six routes and none is vendor-scoped."* **Wrong.** The routes are global *by name* and
scoped *by content*; `scoped_products` / `scoped_orders` were applied to every view on Day 9.
I had inferred an absence from a URL listing without exercising a single endpoint.

The roadmap line I "corrected" on that basis was itself wrong twice over: the area half was
already marked done a few rows above it, so the file contradicted itself. Both are now fixed
with the reasoning recorded, because the failure mode — **a route name is not evidence about
what a route returns** — is the same shape as a check that passes for the wrong reason.

### Verification

- **477 unit tests** — unchanged, all green (this change is dashboard-only; no API surface moved)
- `verify_day9.py` — **49 live assertions**, re-run for the vendor-scoping invariant
- Browser: dashboard **112** (was 103; +9 assertions — four in the vendor section, five
  cross-role, and the `parseRs` self-test retained)
- Screenshots confirm the render, not just the selectors: `shot_15_vendor_home.png` shows the
  vendor banner, Rs. 1,810 and "Your products, all time"; `shot_14_areas.png` shows the admin
  counterpart, "Shop-wide" and "All time"
- Probe user from `verify_day9.py` purged: `admin`, `testuser`, `vendor1` remain

---

## Day 13 Completed (2026-09-22) — the last three P1 gaps, and a bug two panels found

**Theme:** three items `FEATURES.md` still listed as open, closed together because they
share one property — each was **invisible to the existing suite**. The API tests passed
without them, both builds passed without them, and the storefront looked complete without
them.

| # | Piece | Status |
|---|-------|--------|
| 1 | `WishlistItem` model in `products` — one per (user, product), `product` CASCADE | **DONE** — migration `products/0006_wishlistitem.py`, applied |
| 2 | `GET`/`POST /api/products/wishlist/` + `DELETE .../wishlist/<product_id>/` | **DONE** — create-or-**get**, so a double-clicked heart is not a 400 |
| 3 | `is_wishlisted` on the product detail payload | **DONE** — the heart is right on first paint, not after a round-trip |
| 4 | `WishlistContext` + heart on `ProductCard` + `/wishlist` page + navbar count | **DONE** — `wishlistLoaded` is a *loaded* flag, not a loading flag |
| 5 | Multipart image upload — products **and** kits, with preview and thumbnail | **DONE** — `ImageField` + `api.upload()`; `FestivalKit.image` is now in the kit write payload |
| 6 | `GET /api/analytics/areas/` — orders and revenue by delivery area | **DONE** — rows sum to `/analytics/sales/`, vendor-scoped |
| 7 | Dashboard "Orders by Delivery Area" panel | **DONE** — with a share bar, and a badge for an area that no longer exists |
| 8 | 51 new unit tests | **DONE** — 426 total, all passing |
| 9 | `verify_day13.py` — 63 live assertions | **DONE** |
| 10 | 16 new browser assertions | **DONE** — storefront 79 → 85, dashboard 64 → 74 |

### The bug that only a cross-check could find

`scoped_orders` was `Order.objects.filter(items__product__vendor=vendor).distinct()` — a
**join**. A vendor with two of their products in one order produced two rows, so a grouped
`values('shipping_city').annotate(Sum('total_amount'))` counted that order's total twice.
Measured on the seeded data: **2780 where the truth was 1810**.

What makes this worth writing down is that it was **invisible from either side alone**:

- a flat `.aggregate(Sum(...))` on the same queryset was *correct*, so `/analytics/sales/`
  had always been right;
- `.distinct()` does not rescue it — Django applies DISTINCT to the grouped rows, so the
  duplication survives into the aggregate.

It surfaced only because the new panel asserted that its rows sum to the headline figure on
the *other* endpoint. Fixed at the root by scoping with an `Exists` subquery, which produces
no join at all, so `count()`, a flat `aggregate()` and a `values().annotate()` are all
correct by construction. `VendorOrderScopingTests` guards it.

### The dashboard was hiding a third of the catalogue

The admin product list used the project-wide default page size of 12. `Product.Meta.ordering`
is `['-popularity_score', '-created_at']`, so a product created through the dashboard's own
dialog (popularity 0) sorted to the **last** page — the row most likely to need attention was
the one that was hidden. Measured: the dashboard read **"Total Products 12"** against 36 real
rows, and a product created in the dialog never appeared in the table.

Found by the new browser assertion that a created product is visible *unfiltered*. Fixed with
`pagination_class = None`, matching every other admin collection (kits, rituals, vendors,
reviews) — the same argument `AdminReviewListView` already carried: a row on page 2 is
invisible to the only person who can act on it. The storefront's catalogue had this defect too
and was fixed on Day 12, in the other direction, because it *is* browsable content.

### Three verifier bugs found while writing the verifier

- It assumed `POST /api/auth/register/` returned a token. It does not — it returns a success
  message and the new user, so a token has to be obtained by logging in afterwards. The first
  run reported a fatal error instead of a result.
- It asserted the public kit payload carried `items`. It never had; the real keys are
  `item_count`, `original_price` and `total_price`. A verifier asserting a literal it did not
  read fails in a way that reads exactly like a product bug. The expected keys are now read
  off the live response.
- **It modified seeded data.** The kit image check uploaded onto `kits[0]` — the seeded
  *Bratabandha Ceremony Kit* — and never restored the picture, so **running the verifier
  permanently changed the demo data**. It surfaced only from reading `git status` and finding
  an unexpected `media/kits/` directory, then asking the database which files it referenced.
  The check now creates its own scratch kit and deletes it, and two assertions pin that no
  seeded kit points at a test upload and no scratch kit was left behind.

> The general rule, already in `AGENTS.md` §12, is "own every precondition you assert".
> This is its sharper edge: **a verifier must not mutate data it does not own.** Reading
> `git status` and the `media/` directory after a sweep is part of the sweep.

### And one that **passed** for the wrong reason — the most instructive of the four

The dashboard check compares the area-panel revenues against the headline "Total Revenue",
which is the assertion that caught the double-counting bug above. It passed on its first run.
It then failed on a later run with `areas=1.95 headline=0.195`.

The app was right both times. The **parser** was wrong:

```js
String('Rs. 19,500').replace(/[^\d.,-]/g, '')   // -> '.19,500'
  .replace(/,/g, '')                            // -> '.19500'
Number('.19500')                                // -> 0.195
```

Stripping everything outside `[\d.,-]` **keeps the period in `Rs.`**, and the leading dot
turns the number into a decimal fraction. It agreed with the area sum on the first run only
because every figure was then three digits, so the leading dot divided *everything* by 1000
uniformly and the equality survived by accident. The moment the total crossed into four
figures, the accidental agreement broke.

Two things were changed, and both are the point:

- the parser now anchors on a **digit** (`/\d[\d,]*(?:\.\d+)?/`), so a currency prefix cannot
  contribute a stray separator;
- the check **self-tests the parser** against nine known inputs before trusting it, so a
  helper that quietly returns a tenth of the truth fails loudly instead of producing a number
  that happens to match.

> A check that passes for the wrong reason is worse than a missing check, because it is
> recorded as evidence. This is the same failure mode as `verify_day3c.py` asserting
> `count == 12` — which was simultaneously the right answer and a first page that could not be
> distinguished from one — and it is why `AGENTS.md` §12 now says to assert the *invariant*,
> not a number that happens to hold.

### Resume with

```bash
cd backend && ./venv/Scripts/python.exe manage.py test        # 426 tests, all green
./venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000
./venv/Scripts/python.exe verify_day13.py                     # 63 assertions
```

Browser checks — note that on Windows `NODE_PATH` must be a **Windows** path, because Node
resolves it itself and does not understand Git-Bash's `/tmp` mount:

```bash
NODE_PATH='C:\Users\<you>\AppData\Local\Temp\harness\node_modules' \
  node frontend/scripts/storefront_check.mjs      # 118 assertions
NODE_PATH='C:\Users\<you>\AppData\Local\Temp\harness\node_modules' \
  node admin-dashboard/scripts/browser_check.mjs  # 74 assertions
```

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

**Blocks P0:** — **all closed.** Kept as a list so the history is readable.

- ~~A production build of the customer frontend (B1).~~ ✅ Day 1
- ~~Delivery fee in the order total (B2).~~ ✅ Day 1
- ~~A real, ranked, explainable recommendation engine (B3).~~ ✅ Day 2
- ~~**Product demand prediction — entirely absent.**~~ ✅ Day 2 — model, endpoint and
  dashboard panel; trained on synthetic data, labelled as such in three places.
- ~~Vendor role and vendor system — absent.~~ ✅ Day 3 / Day 9
- ~~Admin/customer/area management in the dashboard — absent.~~ ✅ Day 3 / Day 8
- ~~Order tracking surface for the customer beyond a static status badge.~~ ✅ Day 4

**P1:**
- ~~Wishlist / favourites.~~ ✅ **BUILT Day 13** — model, endpoints, card heart, `/wishlist`
  page and a navbar count. See §Day 13.
- ~~Reviews and ratings (no `Review` model exists).~~ ✅ **BUILT Day 11** — model, endpoints,
  storefront section and `/reviews` moderation. See §Day 11.
- ~~Password reset.~~ ✅ **BUILT Day 4**, sessions revoked Day 7.
- ~~Per-vendor and per-area analytics.~~ ✅ **Vendor scoping BUILT Day 9**;
  **per-area breakdown BUILT Day 13** (`/api/analytics/areas/` + a dashboard panel). See §Day 13.
- ~~An image-upload widget — kits and products have an `image` column and no UI sets it.~~
  ✅ **BUILT Day 13** — multipart upload for products and kits, with a preview and a table
  thumbnail. See §Day 13.
- ~~Personalized recommendations from purchase history.~~ ✅ **BUILT Day 2**.
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
| 4 | No demand prediction feature exists at all | **High** | ✅ FIXED Day 2 |
| 5 | Recommendation ranking is not actually ranking (set() ordering) | **Medium** | ✅ FIXED Day 2 |
| 6 | `is_admin_user` unenforced on the API; no VENDOR role | **Medium** | ✅ FIXED Day 3 |
| 7 | `router.push()` during render in checkout | **Medium** | ✅ FIXED Day 1 |
| 8 | Home page masks API failure with hardcoded fallback | **Medium** | ✅ FIXED Day 1 |
| 9 | Hardcoded admin credentials as form defaults | **Medium** | ✅ FIXED Day 1 |
| 10 | Admin product list paginated, hiding rows from the only person who can edit them | **Medium** | ✅ FIXED Day 13 |
| 11 | Vendor analytics double-counted an order holding two of their products | **Medium** | ✅ FIXED Day 13 |

> Rows 4–6 read "Open — Day 2/3" for several days after they were fixed. That is the same
> class of error as a stale test: a status table nobody re-reads is worse than no table, so
> these were reconciled against the Priority section on Day 13.

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
| ~~Wishlist~~ | ✅ **Done Day 13** — see §Day 13 |
| ~~Image upload widget (kits + products have the column, no UI)~~ | ✅ **Done Day 13** — multipart, with preview; `FestivalKit.image` added to the write payload |
| ~~Vendor / per-area analytics~~ | ✅ **Done Day 13** for the per-area half (vendor scoping was Day 9). See §Day 13 |
| ~~Search relevance — `icontains` only, no fuzzy matching~~ | ✅ **Done Day 12** — see §Day 12. Remaining limits listed honestly in `docs/SEARCH.md` §7 |

**Every P1 item is now closed.** The only work left is P2.

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
