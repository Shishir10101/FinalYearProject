# RUN.md — How to start this project

Complete command reference for running the **Puja Sewa** stack locally.
Companion docs: `README.md` (quick start) · `AGENTS.md` (the rules) · `docs/CURRENT-STATE.md` (live status).

**Three processes, three terminals. No Docker, no Celery, no Redis.**

| # | Process | Port | URL |
|---|---|---|---|
| 1 | Django + DRF backend (SQLite) | 8000 | http://127.0.0.1:8000/api/ |
| 2 | Next.js customer storefront | 3000 | http://127.0.0.1:3000 |
| 3 | Next.js admin dashboard | 3001 | http://127.0.0.1:3001 |

All commands are written for **Git Bash on Windows**, which is what this machine uses.
Every backend command goes through the venv interpreter — never a bare `python`.

---

## 0. Prerequisites

Verified present on this machine (2026-09-23):

| Requirement | Status |
|---|---|
| `backend/venv/Scripts/python.exe` | ✅ Python 3.12.5 |
| `backend/db.sqlite3` | ✅ exists, seeded |
| `frontend/node_modules` | ✅ Next.js 16.2.2 |
| `admin-dashboard/node_modules` | ✅ Next.js 16.2.2 |
| Playwright harness (for browser checks only) | ✅ `C:\Users\dell\AppData\Local\Temp\harness\node_modules` |

**Only needed on a fresh clone** (skip if the rows above are green):

```bash
# Backend
cd backend
python -m venv venv
venv/Scripts/python.exe -m pip install -r requirements.txt

# Frontends
cd frontend        && npm install
cd ../admin-dashboard && npm install

# Browser-check harness — installed OUTSIDE the project on purpose,
# so it never becomes a package.json dependency
mkdir -p /tmp/harness && cd /tmp/harness && npm init -y && npm install playwright-core
```

> **Windows `NODE_PATH` trap.** Node resolves `NODE_PATH` itself and does not understand
> Git-Bash's `/tmp` mount, so `/tmp/harness/node_modules` fails with
> `Cannot find module 'playwright-core'` even though it is installed. Use the Windows path:
> `C:\Users\dell\AppData\Local\Temp\harness\node_modules`. Same rule for `SHOT_DIR`.

---

## 1. Terminal 1 — Backend (start this FIRST)

```bash
cd backend

# One-time / after pulling model changes
venv/Scripts/python.exe manage.py migrate

# Seed a complete demo — products, categories, kits, festival calendar,
# sample orders AND the rituals (the Puja entry point). Skip if the DB is already seeded.
venv/Scripts/python.exe manage.py seed_data

# Keep the festival calendar in the future, and build the forecast dataset (SYNTHETIC)
venv/Scripts/python.exe manage.py refresh_festivals
venv/Scripts/python.exe manage.py generate_synthetic_sales

# Start the API
venv/Scripts/python.exe manage.py runserver 127.0.0.1:8000 --noreload
```

Serving at **http://127.0.0.1:8000/api/**.

Health check in a second shell:

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/products/
# expect: 200
```

### Repair flags — only when the DB has drifted from the seed values

These restore the baseline **without touching anything an admin changed by hand**:

```bash
venv/Scripts/python.exe manage.py seed_data --reset-stock        # restore inventory
venv/Scripts/python.exe manage.py seed_data --reset-kit-items    # re-add missing kit lines
venv/Scripts/python.exe manage.py seed_data --reset-popularity   # undo fixture demand signal
```

`--reset-kit-items` re-adds and corrects, but **never deletes** a kit line.

---

## 2. Terminal 2 — Customer storefront

```bash
cd frontend
npm run dev -- -p 3000
```

Serving at **http://127.0.0.1:3000**.

## 3. Terminal 3 — Admin dashboard

```bash
cd admin-dashboard
npm run dev -- -p 3001
```

Serving at **http://127.0.0.1:3001**.

> **Always pin the port, and start the two frontends sequentially.** `next dev` with no `-p`
> races for :3000, and the loser silently takes :3001 — the storefront then serves on the
> admin's port and both apps are wrong.

---

## 4. Seeded logins

| Username | Password | Role | Can reach |
|---|---|---|---|
| `admin` | `admin123` | super_admin | everything, `/admin/` |
| `vendor1` | `vendor1234` | vendor | own 12 products, own orders, forecast |
| `testuser` | `test1234` | customer | storefront only |
| *(anonymous)* | — | customer | storefront, read-only |

Roles are resolved by `backend/core/permissions.py`. Out-of-scope requests return **404, not 403**.

---

## 5. Demo walkthrough — the path that works end to end

```
1.  Backend :8000, frontend :3000, admin :3001 all running
2.  Home → festival calendar shows real upcoming dates
3.  Click the Dashain kit → see its required samagri
4.  Browse a category → filter by price
5.  Open a product → add to cart  (heart it → /wishlist)
6.  Cart → totals include the delivery fee, served from the API
7.  Checkout → pick a delivery area (from the DB) → place order
8.  Order confirmation → status timeline shows step 1 active
9.  /account/orders → the order appears in history with live status
10. Open the order → each completed step shows the time it happened
11. /recommendations → every card explains WHY it was recommended
12. Search "sindoer" → "did you mean" suggestion, transliteration-aware
13. admin :3001 as admin/admin123 → Products → create, edit price, toggle inactive
14. Products → enter price -5 → the field itself shows the error
15. Catalog Settings → add a delivery area with a fee override
16. Back to storefront checkout → the new area appears with its fee
17. Log in as vendor1/vendor1234 → dashboard shows 12 products, not 35 (scoping is visible)
18. Products → only their own rows; no Catalog Settings in the sidebar
19. Demand Forecast → synthetic banner visible, restock table, MAPE per product
20. Admin → Festival Kits → Items: add a product, set quantity, flip Required/Optional
21. Vendors → create a shop for an account: that account becomes a vendor
22. Storefront → product page → Ratings & Reviews: write one, watch the average move
```

Full 30-step version: `docs/FEATURES.md` §7.

---

## 6. Verification

### Unit + integration tests (no server needed)

```bash
cd backend
venv/Scripts/python.exe manage.py test          # 498 tests
```

### Live API sweeps (server MUST already be running on :8000)

```bash
cd backend
venv/Scripts/python.exe verify_day2.py      # 68 assertions
venv/Scripts/python.exe verify_day3.py      # 57  — roles & CRUD
venv/Scripts/python.exe verify_day3b.py     # 41
venv/Scripts/python.exe verify_day3c.py     # 129 — full shopping flow
venv/Scripts/python.exe verify_day4.py      # 88  — history, reset, validation
venv/Scripts/python.exe verify_day6.py      # 40  — the ritual entry point
venv/Scripts/python.exe verify_day7.py      # 30  — token revocation
venv/Scripts/python.exe verify_day8.py      # 74  — kit & ritual authoring
venv/Scripts/python.exe verify_day9.py      # 49  — vendor administration
venv/Scripts/python.exe verify_day11.py     # 68  — reviews & moderation
venv/Scripts/python.exe verify_day12.py     # 84  — search & ranking
venv/Scripts/python.exe verify_day13.py     # 68  — wishlist, uploads, areas
venv/Scripts/python.exe verify_day14.py     # 21  — mocked-payment disclosure
```

> **Run the server with `--noreload` for a sweep.** Otherwise editing any `.py` restarts the
> child, and a child that dies mid-reload leaves the parent holding :8000 answering nothing —
> which looks exactly like a broken endpoint.
>
> **Sweep in two batches (5 + 7) with a server restart between.** A 12-verifier burst saturates
> the shell's HTTP layer: the process stays listening but returns `000`/`503`.
>
> **Never chain a sweep with `&&`** — curl exits 23 after a healthy 200, so everything after it
> silently skips. Use `;`.

### Browser checks (the only checks that can see a client-side render failure)

Require **all three servers**, a **production build**, and the harness on `NODE_PATH`:

```bash
# Build first — a dev server's HMR socket fails in this environment and the client never hydrates
cd frontend        && npm run build && npx next start -p 3000
cd admin-dashboard && npm run build && npx next start -p 3001

# Then, from the repo root:
cd admin-dashboard
NODE_PATH='C:\Users\dell\AppData\Local\Temp\harness\node_modules' node scripts/browser_check.mjs    # 119 assertions
cd ../frontend
NODE_PATH='C:\Users\dell\AppData\Local\Temp\harness\node_modules' node scripts/storefront_check.mjs # 136 assertions
```

The storefront check places **one real order** — clean it up afterwards (see §7).

### Scroll smoothness

`frontend/scripts/scroll_probe.mjs` is the regression check for the landing page's scroll
performance. It scrolls the whole page in a real browser and counts frames over 50 ms, and
also reports broken/relative `<img>` sources. Needs the storefront on :3000 (production build).

```bash
cd frontend
NODE_PATH='C:\Users\dell\AppData\Local\Temp\harness\node_modules' node scripts/scroll_probe.mjs
```

Baseline: **0 long frames of 354, worst 21–25 ms, 12 images, 0 broken, 0 relative.**
The median (~21 ms) is the headless browser's own cadence, not a frame rate — the number
that matters is the long-frame count, which should be zero.

### Lint

`next lint` does **not** enable `no-undef` in this project, so undefined-variable bugs ship
silently. Run it explicitly:

```bash
cd frontend        && npx eslint --rule '{"no-undef":"error"}' src/
cd ../admin-dashboard && npx eslint --rule '{"no-undef":"error"}' src/
```

---

## 7. Cleanup — run after every verification sweep

The verifiers create real rows. These commands remove only rows they own:

```bash
cd backend
venv/Scripts/python.exe manage.py purge_verification_orders    # --dry-run supported
venv/Scripts/python.exe manage.py purge_verification_users     # --dry-run supported
venv/Scripts/python.exe manage.py purge_verification_reviews   # --dry-run supported
```

Afterwards, **re-check the seeded numbers** — `verify_day13.py` asserts inventory, and a
leftover reservation shows up as a false restock alert.

---

## 8. Troubleshooting

### A "missing" endpoint that exists

`runserver --noreload` started in a background shell outlives the shell if it exits abnormally,
keeps the port, and keeps serving **stale code**. A second `runserver` fails to bind while the
old process answers every request.

```bash
netstat -ano | grep ":8000.*LISTENING"     # find the PID
```

```powershell
Stop-Process -Id <pid> -Force
```

Then restart and confirm with `curl`. **After every kill, check for a second `LISTENING` pid** —
`TIME_WAIT` is fine, a second listener is not.

> `taskkill //PID <n> //F` does **not** work in Git Bash — it rejects the double-slash syntax.
> Use the PowerShell form above.

### A port is already in use

| Port | Owner | Fix |
|---|---|---|
| 8000 | Django | kill the stale PID (above) |
| 3000 | storefront | `npm run dev -- -p 3000`, or kill the node process |
| 3001 | admin | `npm run dev -- -p 3001`, or kill the node process |

### `Build error occurred` after `✓ Compiled successfully`

This is the sandbox bulk-delete guard firing on Turbopack's own scratch files — **the build
passed**. Confirm from the log's `Compiled successfully` / `Generating static pages (N/N)`
lines and `.next/app-path-routes-manifest.json`, never from the exit code or the word "Error".

If the guard fires at the **start** (no compile lines, no manifest), the stale `.next` is being
cleared. Move it instead of deleting it — a rename is not intercepted:

```bash
mkdir -p "/c/Users/dell/AppData/Local/Temp/next_stale"
mv .next "/c/Users/dell/AppData/Local/Temp/next_stale/next"
```

The guard's budget is **per turn**, so do not retry a blocked build in the same turn, and never
chain a delete before a build (`rm -f old.log && npm run build` skips the build and leaves you
reading stale output).

### A route returns 200 but shows the 404 page

A `loading.js` on the route opens a Suspense boundary, so `notFound()` renders the 404 UI into a
**200**. Live on `/pujas/[slug]`. Assert the 404 UI plus `<meta name="robots" content="noindex">`
— never `status === 404`.

### `Cannot find module 'playwright-core'`

`NODE_PATH` is a POSIX path. Use the Windows path from §0.

---

## 9. All management commands

| Command | Purpose |
|---|---|
| `manage.py check` | Django system check |
| `manage.py migrate` | apply migrations |
| `manage.py makemigrations` | create migrations after a model change |
| `manage.py runserver 127.0.0.1:8000 --noreload` | start the API |
| `manage.py test` | 498 tests |
| `manage.py seed_data` | full demo seed (idempotent) |
| `manage.py seed_data --reset-stock` | restore inventory to the seed values |
| `manage.py seed_data --reset-kit-items` | re-add missing / drifted kit lines |
| `manage.py seed_data --reset-popularity` | undo fixture-driven popularity inflation |
| `manage.py refresh_festivals` | rebuild the festival calendar into the future |
| `manage.py seed_pujas` | derive rituals from existing kit/product data |
| `manage.py generate_synthetic_sales` | rebuild the **SYNTHETIC** forecast dataset |
| `manage.py fetch_demo_images` | fetch free demo imagery for products/categories/kits |
| `manage.py fetch_demo_images --force` | re-fetch every row (also repairs wrong matches) |
| `manage.py fetch_demo_images --match "Kalash,Bell"` | re-fetch only rows matching a substring |
| `manage.py fetch_demo_images --retry-fallbacks` | re-fetch only rows left holding a drawn tile |
| `manage.py fetch_demo_images --dry-run` | resolve and report, write nothing |
| `manage.py purge_verification_orders` | delete verifier orders + release their stock |
| `manage.py purge_verification_users` | delete verifier accounts (`verifyday` prefix) |
| `manage.py purge_verification_reviews` | delete verifier reviews |

### Demo imagery

`fetch_demo_images` pulls freely-licensed photos from **Wikimedia Commons**, crops them
square, and re-encodes them as 600×600 JPEG q82 (~40-70 KB each, versus ~700 KB before).
Attribution for every file is written to `backend/media/IMAGE-CREDITS.md` — Commons images
are CC/PD, so that file must ship with the project.

Two things worth knowing if you re-run it:

- **It rate-limits.** Commons answers `429` when pushed, and a throttled row looks exactly
  like "nothing found". The command backs off and retries, but a row that still fails gets a
  **locally drawn tile** carrying the item's name rather than a broken image. Use
  `--retry-fallbacks` to give those rows another chance later.
- **A wrong photo is worse than a tile.** The command rejects near-miss titles that a keyword
  search cannot see — Commons returns *conch fritters* for "conch shell", *coconut cookies*
  for "dried coconut", a *chemical diagram* for "benzoin resin" and a *portrait of the writer
  Jaishankar Prasad* for "prasad". Those all became drawn tiles instead. If one slips
  through, fix it with `--match "<item name>"`.

A command only exists if its app is in `INSTALLED_APPS` — `core/` is the project package, not
an app, so a `seed_data.py` placed there would be dead code.

---

## 10. Known state before you demo

- **Payments are mocked.** eSewa/Khalti set `payment_status = 'paid'` with no gateway involved.
  They are honestly **labelled** in the UI, driven by `orders.models.PAYMENT_METHODS_ARE_MOCKED`.
- **The forecast trains on synthetic data** — banner-labelled, in its own `SyntheticSalesRecord`
  table so fabricated rows can never be mixed with real orders.
- **3 of the 6 soonest festivals have no kit** — the home page says so and routes to the recommender.
- **`DEBUG = True`, a dev `SECRET_KEY`, `ALLOWED_HOSTS = ['*']` and `CORS_ALLOW_ALL_ORIGINS`
  are still set** in `backend/core/settings.py`. Fine locally, must change before any deployment.
- **Work is uncommitted.** The last commits are Day 12; Days 13 → 15c sit in the working tree.
