/**
 * Real-browser check of the admin dashboard.
 *
 * Why this exists: every other check in this project talks to the API or inspects
 * the compiled output. Neither can see a React component fail to render. The
 * dashboard's `AuthGate` renders "Checking your session…" during SSR, so `curl`
 * cannot get past it either — a page whose client render throws returns a
 * perfectly healthy 200 with an empty shell.
 *
 * This project has already shipped that class of bug: four `Catalog Settings`
 * buttons that threw `ReferenceError` before their dialog opened, and a home-page
 * "+" button that looked like add-to-cart and had no handler. Both compiled
 * cleanly and linted cleanly.
 *
 * It **seeds one review through the API** to exercise the `/reviews` moderation round
 * trip, because the page deliberately offers no way to author one, and removes it again
 * before exiting — a stray review would silently move a seeded product's rating, and
 * `verify_day11.py` asserts a clean slate on that same product. If the run is
 * interrupted mid-section, clean up with `manage.py purge_verification_reviews`.
 *
 * Uses the Edge/Chrome already on the machine via `playwright-core`, so there is no
 * ~500 MB Chromium download and nothing added to the project's dependencies.
 *
 * Setup (once, outside the project so package.json stays untouched):
 *
 *   mkdir -p /tmp/harness && cd /tmp/harness
 *   npm init -y && npm install playwright-core
 *
 * Run (dashboard on :3001, API on :8000):
 *
 *   cd admin-dashboard
 *   NODE_PATH=/tmp/harness/node_modules node scripts/browser_check.mjs
 *
 * **On Windows, `NODE_PATH` must be a Windows path.** Git-Bash's `/tmp` is a mount,
 * not a real directory, and Node resolves `NODE_PATH` itself — so the line above
 * fails with `Cannot find module 'playwright-core'` although the package is
 * installed. Resolve it once with `pwd -W` inside the harness directory:
 *
 *   NODE_PATH='C:\Users\<you>\AppData\Local\Temp\harness\node_modules' \
 *     node scripts/browser_check.mjs
 *
 * Environment: `ADMIN_BASE` overrides the dashboard URL, `SHOT_DIR` the directory
 * screenshots are written to (defaults to the working directory). Node cannot read a
 * Git-Bash path like `/c/Users/...` — pass a Windows path for `SHOT_DIR`.
 */

import { createRequire } from 'node:module';

// Loaded through CJS resolution on purpose. A bare `import 'playwright-core'` is ESM
// resolution, which ignores NODE_PATH and only looks up from *this file's* directory —
// so the documented `NODE_PATH=<harness>/node_modules node scripts/browser_check.mjs`
// failed with ERR_MODULE_NOT_FOUND even though the package was there. `createRequire`
// honours NODE_PATH, so the harness runs from anywhere with the dependency installed
// outside the project.
const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');

// Used to write a real 1x1 PNG to disk, because `setInputFiles` needs a path and the
// backend's ImageField rejects anything that is not a decodable image.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ADMIN = process.env.ADMIN_BASE || 'http://127.0.0.1:3001';
const API = process.env.API_BASE || 'http://127.0.0.1:8000';
const SHOTS = process.env.SHOT_DIR || '.';
const USERNAME = 'admin';
const PASSWORD = 'admin123';

// Django's `MEDIA_ROOT`. Deleting a Product through the API removes the row and does
// **not** unlink the uploaded file, so the image-upload section has to remove its own
// file explicitly or it leaks one per run. Resolved from this script's own location so
// the harness works from any working directory.
const MEDIA_ROOT = process.env.MEDIA_ROOT || path.resolve(
  path.dirname(fileURLToPath(import.meta.url)), '..', '..', 'backend', 'media',
);

let pass = 0;
let fail = 0;
const failures = [];
const consoleErrors = [];

function check(label, ok, detail = '') {
  if (ok) {
    pass += 1;
    console.log(`  PASS  ${label}`);
  } else {
    fail += 1;
    failures.push(label);
    console.log(`  FAIL  ${label}  ${detail}`);
  }
}

function section(title) {
  console.log(`\n=== ${title} ===`);
}

/**
 * A direct call to the API, used only to *seed* state the dashboard cannot create.
 *
 * The reviews page has `canCreate: false` on purpose — a manager moderates reviews,
 * they never write them — so the only honest way to give the Hide/Show round trip a
 * row to work on is to post one as the customer, through the same endpoint the
 * storefront uses.
 */
async function api(method, path, token, body) {
  const res = await fetch(`${API}${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await res.text();
  let parsed = null;
  try { parsed = text ? JSON.parse(text) : null; } catch { parsed = text; }
  return { status: res.status, body: parsed };
}

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  // Any uncaught exception in the React tree shows up here. This is the signal a
  // build and an API test both cannot produce.
  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const url = (msg.location() && msg.location().url) || '';
    consoleErrors.push(`${msg.text()} @ ${url}`);
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  // ---------------------------------------------------------------- login
  section('Sign in');

  await page.goto(`${ADMIN}/login`, { waitUntil: 'domcontentloaded' });
  await page.fill('#username', USERNAME);
  await page.fill('#password', PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }),
    page.click('button[type="submit"]'),
  ]);
  check('login leaves the login page', !page.url().includes('/login'), page.url());

  // The sidebar is the proof the token was verified against the API, not just
  // read out of localStorage.
  await page.waitForSelector('.sidebar', { timeout: 20000 });
  check('the sidebar renders, so the token was verified', await page.isVisible('.sidebar'));

  const navLabels = await page.$$eval('.sidebar nav a', (els) => els.map((e) => e.textContent.trim()));
  check('Rituals is in the navigation', navLabels.some((l) => l.includes('Rituals')), navLabels.join(' | '));
  check('Vendors is in the navigation', navLabels.some((l) => l.includes('Vendors')), navLabels.join(' | '));
  check('Reviews is in the navigation', navLabels.some((l) => l.includes('Reviews')), navLabels.join(' | '));

  // ---------------------------------------------------------------- kits
  section('/festivals — kits render and the item editor opens');

  await page.goto(`${ADMIN}/festivals`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.table tbody tr', { timeout: 20000 });

  const kitRows = await page.locator('.table tbody tr').count();
  check('the kits table renders rows', kitRows > 0, `rows=${kitRows}`);

  const kitHeading = await page.locator('h1').first().textContent();
  check('the heading is the kits page, not an error state',
    kitHeading.includes('Festival'), kitHeading);

  const itemButtons = page.getByRole('button', { name: 'Items', exact: true });
  check('every kit row offers the Items control', await itemButtons.count() === kitRows,
    `${await itemButtons.count()} controls for ${kitRows} rows`);

  await page.screenshot({ path: `${SHOTS}/shot_1_kits.png`, fullPage: true });

  // Open the item editor on the first kit — this is the Day 8 component whose
  // client render had never been observed.
  await itemButtons.first().click();
  await page.waitForSelector('input#im-search', { timeout: 20000 });
  check('the item editor opens', await page.isVisible('input#im-search'));
  check('the item editor has its own table', await page.locator('.table-panel .table').count() === 1);
  check('the "add a product" picker is present',
    await page.locator('#im-search').isEditable());

  const itemRows = await page.locator('.table-panel tbody tr').count();
  check('the item editor lists the kit\'s samagri', itemRows > 0, `items=${itemRows}`);

  const summary = await page.locator('.table-panel').getByText(/item[s]? ·/).first().textContent();
  check('it reports an item count and a required count', /\d+ items? · \d+ required/.test(summary), summary);

  await page.screenshot({ path: `${SHOTS}/shot_2_item_editor.png`, fullPage: true });

  // The product search is a live API call; if the picker is wired it returns rows.
  await page.fill('#im-search', 'dhoop');
  // Wait for a *result* button specifically. Waiting for `.table-panel button`
  // resolves instantly against the item table's own Remove buttons, so the check
  // would run before the debounced search had returned.
  let searchResults = 0;
  try {
    await page.waitForSelector('.table-panel button:has-text("Rs.")', { timeout: 20000 });
    searchResults = await page.locator('.table-panel button:has-text("Rs.")').count();
  } catch { /* reported below */ }
  check('the product search returns live results', searchResults > 0, `results=${searchResults}`);
  await page.screenshot({ path: `${SHOTS}/shot_3_product_search.png`, fullPage: true });

  // ---------------------------------------------------------------- rituals
  section('/pujas — the new page');

  await page.goto(`${ADMIN}/pujas`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.table tbody tr', { timeout: 20000 });

  const pujaRows = await page.locator('.table tbody tr').count();
  check('the rituals table renders rows', pujaRows >= 8, `rows=${pujaRows}`);
  check('the rituals page has no Items control when nothing is expanded',
    await page.locator('.table-panel').count() === 0);

  const pujaBody = await page.locator('.table tbody').textContent();
  check('it reports a kitless ritual honestly',
    pujaBody.includes('No kit yet'), 'expected at least one "No kit yet"');

  await page.screenshot({ path: `${SHOTS}/shot_4_rituals.png`, fullPage: true });

  // The ritual form must offer the whole enum, not just the types in use.
  await page.getByRole('button', { name: '+ New Ritual' }).click();
  await page.waitForSelector('#dm-occasion_type', { timeout: 20000 });
  const occasionOptions = await page.$$eval('#dm-occasion_type option', (o) => o.map((x) => x.value));
  check('the ritual form draws its occasion list from the API enum',
    occasionOptions.includes('nag_panchami') && occasionOptions.includes('other'),
    occasionOptions.join(','));
  check('a ritual cannot be given a kit from this form',
    await page.locator('#dm-kit').count() === 0,
    'a kit field appeared — the FK is on the kit, not the ritual');
  await page.screenshot({ path: `${SHOTS}/shot_5_new_ritual.png`, fullPage: true });
  await page.keyboard.press('Escape');

  // ---------------------------------------------------------------- vendors
  section('/vendors — the new page');

  await page.goto(`${ADMIN}/vendors`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.table tbody tr', { timeout: 20000 });

  const vendorRows = await page.locator('.table tbody tr').count();
  check('the vendors table renders rows', vendorRows >= 1, `rows=${vendorRows}`);

  const vendorBody = await page.locator('.table tbody').textContent();
  check('the seeded vendor is listed', vendorBody.includes('Patan Puja Bhandar'), vendorBody.slice(0, 200));
  check('its owning account is shown', vendorBody.includes('vendor1'), vendorBody.slice(0, 200));

  const vendorButtons = await page.$$eval('.table tbody button', (els) => els.map((e) => e.textContent.trim()));
  check('a vendor row has no Items control',
    await page.getByRole('button', { name: 'Items', exact: true }).count() === 0,
    `itemsUrl should be absent for vendors; row buttons were: ${vendorButtons.join(' | ')}`);

  await page.screenshot({ path: `${SHOTS}/shot_6_vendors.png`, fullPage: true });

  await page.getByRole('button', { name: '+ New Vendor' }).click();
  await page.waitForSelector('#dm-user', { timeout: 20000 });

  const optionsOf = (sel) => page.$$eval(`${sel} option`, (o) => o.map((x) => x.value).filter(Boolean));
  const waitForOptions = async (sel) => {
    for (let i = 0; i < 40; i += 1) {
      const opts = await optionsOf(sel);
      if (opts.length) return opts;
      await page.waitForTimeout(250);
    }
    return [];
  };

  const accountOptions = await waitForOptions('#dm-user');
  check('the owning-account picker is populated from the API', accountOptions.length > 0,
    `options=${accountOptions.join(',')}`);

  const areaOptions = await waitForOptions('#dm-area');
  check('the assigned-area picker lists the three seeded areas', areaOptions.length === 3,
    `options=${areaOptions.join(',')}`);

  // The owning account is offered once and then fixed — reassigning a shop would
  // silently transfer everything that account owns.
  await page.screenshot({ path: `${SHOTS}/shot_7_new_vendor.png`, fullPage: true });
  await page.keyboard.press('Escape');

  await page.getByRole('button', { name: 'Edit', exact: true }).first().click();
  await page.waitForSelector('#dm-user', { timeout: 20000 });
  check('editing a vendor freezes the owning account',
    await page.locator('#dm-user').isDisabled(),
    'the account picker should be disabled when editing');
  check('editing still allows the area to change',
    await page.locator('#dm-area').isEnabled());
  await page.screenshot({ path: `${SHOTS}/shot_8_edit_vendor.png`, fullPage: true });
  await page.keyboard.press('Escape');

  // ---------------------------------------------------------------- reviews
  section('/reviews — moderation is a config, not a fork');

  // Seed a row through the API: the page deliberately offers no "New review"
  // (a manager must not put words in a customer's mouth), so there is nothing to
  // moderate until a customer writes one. This mirrors the storefront exactly.
  const customerLogin = await api('POST', '/api/auth/login/', null,
    { username: 'testuser', password: 'test1234' });
  const customerToken = customerLogin.body && customerLogin.body.access;
  check('a customer token was obtained to seed a review', !!customerToken,
    `status=${customerLogin.status}`);

  const productList = await api('GET', '/api/products/?page=1');
  const seedProduct = (productList.body && productList.body.results && productList.body.results[0]) || null;
  check('a product was found to review', !!seedProduct, `status=${productList.status}`);

  let seededReviewId = null;
  if (customerToken && seedProduct) {
    const created = await api('POST', `/api/products/${seedProduct.slug}/reviews/`, customerToken, {
      rating: 2,
      title: 'Seeded row for the moderation check',
      body: 'Seeded by browser_check.mjs — safe to delete.',
    });
    check('a review was seeded for the Hide/Show round trip', created.status === 201,
      `status=${created.status} body=${JSON.stringify(created.body).slice(0, 160)}`);
    seededReviewId = created.body && created.body.id;
  }

  if (!seededReviewId) {
    console.log('  cannot continue without a seeded review — the moderation checks below are skipped');
  } else {
    await page.goto(`${ADMIN}/reviews`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.table tbody tr', { timeout: 20000 });

    const reviewHeading = await page.locator('h1').first().textContent();
    check('the heading is the reviews page, not an error state',
      reviewHeading.trim() === 'Reviews', reviewHeading);

    const reviewBody = await page.locator('.table tbody').innerText();
    check('the seeded review is listed with its product',
      reviewBody.includes(seedProduct.name), reviewBody.slice(0, 200));
    check('and names the reviewer', reviewBody.includes('testuser'), reviewBody.slice(0, 200));
    check('it reads as published to begin with', /Published/i.test(reviewBody),
      reviewBody.slice(0, 200));

    // The two affordances this page must NOT have. `canCreate: false` removes the
    // button rather than letting the API reject it, and `canEdit: false` removes
    // Edit — a manager who could rewrite a review could also rewrite the badge.
    check('there is no "New review" button',
      await page.getByRole('button', { name: /New review/i }).count() === 0,
      'a manager should never author a review');
    check('there is no Edit control on a review row',
      await page.getByRole('button', { name: 'Edit', exact: true }).count() === 0,
      'the row offered an Edit button');
    check('but there is a Delete control',
      await page.getByRole('button', { name: 'Delete', exact: true }).count() > 0);

    await page.screenshot({ path: `${SHOTS}/shot_10_reviews.png`, fullPage: true });

    // --- hide ---------------------------------------------------------
    await page.getByRole('button', { name: 'Hide', exact: true }).first().click();
    let hid = true;
    try {
      await page.waitForFunction(
        () => /Hidden/.test(document.querySelector('.table tbody')?.innerText || ''),
        { timeout: 15000 },
      );
    } catch { hid = false; }
    check('Hide flips the visibility badge to Hidden', hid, 'the badge never changed');
    check('the button becomes "Show" so the action is reversible',
      await page.getByRole('button', { name: 'Show', exact: true }).count() > 0,
      'no way back — hiding would be a one-way door');

    // Wait for the flash rather than reading straight away. The row flips optimistically,
    // so the badge changes before the PATCH has even been answered — and the flash is
    // raised only once it has. Reading immediately is a race the flash loses.
    // (It also clears itself after 4s, so it has to be caught, not looked up later.)
    let hideFlash = true;
    try {
      await page.waitForFunction(
        () => /hidden from the storefront/i.test(document.body.innerText),
        { timeout: 15000 },
      );
    } catch { hideFlash = false; }
    check('a confirmation names what happened', hideFlash, 'no flash message');

    await page.screenshot({ path: `${SHOTS}/shot_11_review_hidden.png`, fullPage: true });

    // --- show ---------------------------------------------------------
    await page.getByRole('button', { name: 'Show', exact: true }).first().click();
    let shown = true;
    try {
      await page.waitForFunction(
        () => /Published/.test(document.querySelector('.table tbody')?.innerText || ''),
        { timeout: 15000 },
      );
    } catch { shown = false; }
    check('Show puts it back on the storefront', shown, 'the badge never came back');

    let showFlash = true;
    try {
      await page.waitForFunction(
        () => /visible again/i.test(document.body.innerText),
        { timeout: 15000 },
      );
    } catch { showFlash = false; }
    check('and the flash says so', showFlash, 'no flash message');

    // The delete dialog, without confirming it. Its whole job is to steer a manager
    // to Hide instead, and that copy is worth asserting.
    await page.getByRole('button', { name: 'Delete', exact: true }).first().click();
    await page.waitForSelector('[role="dialog"]', { timeout: 15000 });
    const dialogText = await page.locator('[role="dialog"]').innerText();
    check('the delete dialog warns that it cannot be undone',
      /cannot be undone/i.test(dialogText), dialogText.slice(0, 200));
    check('and points at Hide as the reversible option',
      /Hide/i.test(dialogText), dialogText.slice(0, 200));
    check('it says the rating will be recalculated without it',
      /rating/i.test(dialogText), dialogText.slice(0, 200));
    await page.screenshot({ path: `${SHOTS}/shot_12_delete_review.png`, fullPage: true });
    await page.keyboard.press('Escape');
    await page.waitForSelector('[role="dialog"]', { state: 'detached', timeout: 15000 }).catch(() => {});
  }

  // Clean up through the API rather than the UI: the row must not survive this run.
  // A stray review silently moves a seeded product's rating, and `verify_day11.py`
  // asserts a clean slate on the very product this seeded onto.
  if (seededReviewId) {
    const deleted = await api('DELETE', `/api/products/reviews/${seededReviewId}/`, customerToken);
    check('the seeded review was removed again', deleted.status === 204, `status=${deleted.status}`);

    // Read it back through the *public* endpoint. Asking the manager-only list with a
    // customer token returns 403, which would satisfy a "not 200" assertion without
    // proving anything — a guard that passes for the wrong reason is worse than none.
    const remaining = await api('GET', `/api/products/${seedProduct.slug}/reviews/`, customerToken);
    check('the product is back to no reviews, so the next verifier sees a clean slate',
      remaining.status === 200 && remaining.body && remaining.body.count === 0,
      `status=${remaining.status} count=${remaining.body && remaining.body.count}`);
  }

  // ---------------------------------------------------------------- vendor role
  section('A vendor can actually open the dashboard, and is scoped');

  // This is the check that found the bug. The API enforced the VENDOR role
  // correctly on every endpoint, but `AdminContext` gated on `is_admin_user` — a
  // legacy boolean only ever set for super_admin/admin — so a vendor's token
  // verified, was thrown away, and the login bounced back here. The role existed
  // on the server and was unreachable in the product.
  const vendorContext = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const vendorPage = await vendorContext.newPage();
  const vendorErrors = [];
  vendorPage.on('pageerror', (err) => vendorErrors.push(err.message));

  await vendorPage.goto(`${ADMIN}/login`, { waitUntil: 'domcontentloaded' });
  await vendorPage.fill('#username', 'vendor1');
  await vendorPage.fill('#password', 'vendor1234');
  await Promise.all([
    vendorPage.waitForURL((url) => !url.pathname.startsWith('/login'), { timeout: 20000 }),
    vendorPage.click('button[type="submit"]'),
  ]).catch(() => {});

  check('a vendor login leaves the login page',
    !vendorPage.url().includes('/login'), vendorPage.url());

  let vendorSidebar = false;
  try {
    await vendorPage.waitForSelector('.sidebar', { timeout: 15000 });
    vendorSidebar = await vendorPage.isVisible('.sidebar');
  } catch { /* reported below */ }
  check('a vendor gets a dashboard, not a bounce back to login', vendorSidebar, vendorPage.url());

  const vendorNav = await vendorPage.$$eval('.sidebar nav a', (els) => els.map((e) => e.textContent.trim()));
  check('a vendor sees Products and Orders', 
    vendorNav.some((l) => l.includes('Products')) && vendorNav.some((l) => l.includes('Orders')),
    vendorNav.join(' | '));
  check('a vendor does NOT see Vendors', !vendorNav.some((l) => l.includes('Vendors')),
    vendorNav.join(' | '));
  check('a vendor does NOT see Catalog Settings', !vendorNav.some((l) => l.includes('Catalog')),
    vendorNav.join(' | '));
  check('a vendor does NOT see Reviews', !vendorNav.some((l) => l.includes('Reviews')),
    vendorNav.join(' | '));

  const vendorRole = await vendorPage.locator('.sidebar .badge').first().textContent().catch(() => '');
  check('the sidebar labels them a Vendor, not an Administrator',
    vendorRole.trim() === 'Vendor', vendorRole.trim());

  await vendorPage.goto(`${ADMIN}/products`, { waitUntil: 'domcontentloaded' });
  await vendorPage.waitForSelector('.table tbody tr', { timeout: 20000 });
  const vendorRowsSeen = await vendorPage.locator('.table tbody tr').count();
  check('the vendor sees a scoped product list', vendorRowsSeen > 0, `rows=${vendorRowsSeen}`);

  // A vendor *may* add products — that is vendor self-service, and the server
  // attributes them to that vendor (`AdminProductListCreateView.perform_create`).
  // The invariant is not "no create button"; it is that a vendor never sees or
  // touches anyone else's stock. The seeded catalogue has 35 products and 12 of
  // them belong to vendor1, so a full list here would be the leak.
  check('the list is scoped, not the whole 35-product catalogue',
    vendorRowsSeen < 35, `rows=${vendorRowsSeen}`);

  const ownerColumn = await vendorPage.$$eval('.table tbody tr', (rows) =>
    rows.map((r) => (r.children[2] ? r.children[2].textContent.trim() : '')));
  check('every row belongs to this vendor and nobody else',
    ownerColumn.length > 0 && ownerColumn.every((v) => v === 'Patan Puja Bhandar'),
    [...new Set(ownerColumn)].join(' | '));

  // And the form must not let them hand ownership to someone else.
  await vendorPage.getByRole('button', { name: '+ New Product' }).click();
  await vendorPage.waitForSelector('#p-vendor', { timeout: 20000 });
  check('the vendor field on the product form is fixed to their own shop',
    await vendorPage.locator('#p-vendor').isDisabled(),
    'a vendor could reassign ownership');
  const fixedShop = await vendorPage.locator('#p-vendor').inputValue();
  check('and it reads as their shop', fixedShop === 'Patan Puja Bhandar', fixedShop);
  await vendorPage.keyboard.press('Escape');

  await vendorPage.screenshot({ path: `${SHOTS}/shot_9_vendor_view.png`, fullPage: true });

  // ---------------------------------------------------------------- vendor home
  // The dashboard home was the one page in this section the vendor never visited, and
  // it is the only page whose numbers change meaning by role. `/analytics/sales/` has
  // returned `scope: 'all' | 'vendor'` since Day 9 and **nothing in the client read
  // it**; the Total Revenue card was captioned with the literal string "All time" for
  // every role, so a vendor was shown a vendor-scoped total under a label claiming it
  // was their all-time shop revenue. The API was correct throughout — the screen was
  // the thing that was wrong, which is exactly the class of bug no API check can see.
  //
  // Read the number here as a vendor so the next assertion can prove it differs.
  await vendorPage.goto(`${ADMIN}/`, { waitUntil: 'domcontentloaded' });
  let vendorHomeReady = false;
  try {
    await vendorPage.waitForSelector('[data-testid="analytics-scope"]', { timeout: 20000 });
    vendorHomeReady = true;
  } catch { /* reported below */ }
  check('a vendor loading the dashboard home gets a scope banner', vendorHomeReady,
    'no [data-testid=analytics-scope] appeared');

  const vendorScope = vendorHomeReady
    ? await vendorPage.locator('[data-testid="analytics-scope"]').getAttribute('data-scope')
    : null;
  check('the banner reports vendor scope, taken from the payload',
    vendorScope === 'vendor', `data-scope=${vendorScope}`);

  const vendorScopeText = vendorHomeReady
    ? await vendorPage.locator('[data-testid="analytics-scope"]').innerText()
    : '';
  check('the banner says the figures are limited to their own products',
    /only orders containing your own products/i.test(vendorScopeText),
    vendorScopeText.slice(0, 160));

  const vendorRevenueCaption = await vendorPage
    .locator('[data-testid="total-revenue-caption"]').innerText().catch(() => '');
  check('the Total Revenue caption no longer claims this is all-time shop revenue',
    /your products/i.test(vendorRevenueCaption) && !/^all time$/i.test(vendorRevenueCaption.trim()),
    vendorRevenueCaption.trim());

  // Raw text only. `parseRs` is declared further down inside this same function, so
  // calling it here would be a temporal-dead-zone ReferenceError — and the comparison
  // it needs to feed happens down there, where the admin figure is read.
  const vendorRevenueText = await vendorPage
    .locator('.stat-card', { hasText: 'Total Revenue' })
    .locator('.stat-value').first().innerText().catch(() => '');

  await vendorPage.screenshot({ path: `${SHOTS}/shot_15_vendor_home.png`, fullPage: true });

  // ---------------------------------------------------------------- back to admin
  // Return to the admin session for the remaining sections. The vendor context is
  // closed below; `page` was signed in as `admin` and is untouched by all of this.

  // Hiding a nav item is a UX convenience, not access control. Reaching the route
  // directly must fail too — and fail as an error state, not as an empty table that
  // looks like "there is nothing to moderate". This is the last page the vendor visits,
  // so nothing below depends on navigating back to a scoped list.
  await vendorPage.goto(`${ADMIN}/reviews`, { waitUntil: 'domcontentloaded' });
  await vendorPage.waitForTimeout(3000);
  const vendorReviewText = await vendorPage.locator('body').innerText();
  check('a vendor reaching /reviews directly is refused by the API',
    /could not load|forbidden|permission|not allowed|403/i.test(vendorReviewText),
    vendorReviewText.slice(0, 200));
  check('and sees no review rows',
    await vendorPage.locator('.table tbody tr').count() === 0,
    'a vendor was shown moderation data');

  // Being refused a page must not read as "your session ended" — a 403 that dumps you
  // back on the login screen looks like a broken login, not a permission boundary.
  const stillSignedIn = await vendorPage.isVisible('.sidebar').catch(() => false);
  check('the vendor is still signed in afterwards, not bounced to login',
    stillSignedIn && !vendorPage.url().includes('/login'),
    `sidebar=${stillSignedIn} url=${vendorPage.url()}`);

  await vendorPage.screenshot({ path: `${SHOTS}/shot_13_vendor_reviews.png`, fullPage: true });

  check('no uncaught client error in the vendor session', vendorErrors.length === 0,
    vendorErrors.slice(0, 2).join(' || '));

  await vendorContext.close();

  // ---------------------------------------------------------------- areas
  section('/ — the per-area breakdown agrees with the headline revenue');

  await page.goto(`${ADMIN}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3000);

  const dashboardText = await page.locator('body').innerText();
  check('the dashboard has an Orders by Delivery Area panel',
    /Orders by Delivery Area/i.test(dashboardText),
    dashboardText.slice(0, 200));

  // The panel and the Total Revenue stat come from two different endpoints. If they
  // disagree, both numbers become untrustworthy — so this compares what is actually
  // rendered, not what the API said in isolation.
  //
  // **This parser was the bug the first time it ran, and the check passed anyway.**
  // The previous version stripped every character outside `[\d.,-]`, which *keeps the
  // period in "Rs."* — so `"Rs. 19,500"` became `".19,500"` → `".19500"` → `0.195`.
  // It agreed with the area sum on the first run only because every figure was then
  // three digits, so the leading dot divided everything by 1000 uniformly and the
  // comparison held by accident. As soon as the total crossed into four figures the
  // accidental agreement broke and the check failed — correctly reporting that its
  // own inputs were nonsense.
  //
  // The fix anchors on a **digit**, so a currency prefix cannot contribute a stray
  // separator: `\d[\d,]*(\.\d+)?` picks out `19,500` and ignores the `Rs.` entirely.
  // `assertParserSane()` below pins it, because a helper that quietly returns a
  // tenth of the truth is worse than no helper — it makes a passing check meaningless.
  const parseRs = (text) => {
    if (text === null || text === undefined) return null;
    const match = String(text).match(/\d[\d,]*(?:\.\d+)?/);
    if (!match) return null;
    const n = Number(match[0].replace(/,/g, ''));
    return Number.isFinite(n) ? n : null;
  };

  // Self-test. Runs before the comparison, so a broken parser fails loudly here rather
  // than producing a number that happens to match.
  const parserCases = [
    ['Rs. 19,500', 19500],
    ['Rs. 7,600', 7600],
    ['Rs. 1,290', 1290],
    ['Rs. 950', 950],
    ['Rs. 0', 0],
    ['39%', 39],
    ['30.4%', 30.4],
    ['', null],
    [null, null],
  ];
  const parserBad = parserCases
    .filter(([input, expected]) => parseRs(input) !== expected)
    .map(([input, expected]) => `${JSON.stringify(input)} -> ${parseRs(input)} (want ${expected})`);
  check('the Rs. parser is sane before it is trusted', parserBad.length === 0,
    parserBad.join('; '));

  // Wait for the panel to have actually rendered its numbers before reading them.
  // A fixed timeout is a guess; this waits on the thing being asserted.
  let areaRendered = true;
  try {
    await page.waitForFunction(() => {
      const stat = [...document.querySelectorAll('.stat-card')]
        .find((c) => /Total Revenue/i.test(c.innerText));
      const value = stat && stat.querySelector('.stat-value');
      const rows = [...document.querySelectorAll('.card')]
        .filter((c) => /Orders by Delivery Area/i.test(c.innerText))
        .flatMap((c) => [...c.querySelectorAll('table.table tbody tr')]);
      return Boolean(value && value.innerText.trim()) && rows.length > 0;
    }, { timeout: 20000 });
  } catch { areaRendered = false; }
  check('the dashboard rendered its revenue figures', areaRendered,
    'the Total Revenue stat or the area table never populated');

  const revenueStat = await page.locator('.stat-card', { hasText: 'Total Revenue' })
    .locator('.stat-value').first().innerText().catch(() => null);

  const areaRows = await page.locator('.card', { hasText: 'Orders by Delivery Area' })
    .locator('table.table tbody tr').all();

  check('the area table lists at least one area', areaRows.length > 0,
    `rows=${areaRows.length}`);

  let areaSum = 0;
  const unparseable = [];
  for (const row of areaRows) {
    const cells = await row.locator('td').allInnerTexts();
    // [area, orders, cancelled, revenue, share]
    const revenue = parseRs(cells[3]);
    if (revenue === null) { unparseable.push(cells[0]); continue; }
    areaSum += revenue;
  }

  const headline = parseRs(revenueStat);
  check('every area row renders a parseable revenue figure', unparseable.length === 0,
    `could not read a revenue figure for: ${unparseable.join(', ')}`);
  check('the Total Revenue stat renders a figure', headline !== null,
    `stat text was ${JSON.stringify(revenueStat)}`);
  check('the area revenues sum to the headline Total Revenue',
    unparseable.length === 0 && headline !== null && Math.abs(areaSum - headline) < 0.01,
    `areas=${areaSum} headline=${headline} rows=${areaRows.length}`);

  // Cross-role. A scope banner over a figure identical to the admin's would be pure
  // decoration — the point is that the two audiences genuinely see different numbers.
  // Seeded data makes this concrete: 8 orders exist, 12 of the 35 products belong to
  // vendor1, and only 3 orders contain any of them.
  const adminScopeAttr = await page
    .locator('[data-testid="analytics-scope"]').getAttribute('data-scope').catch(() => null);
  check('the admin dashboard is labelled shop-wide, not vendor',
    adminScopeAttr === 'all', `data-scope=${adminScopeAttr}`);

  const adminCaption = await page
    .locator('[data-testid="total-revenue-caption"]').innerText().catch(() => '');
  check('the admin caption is the plain all-time one',
    /^all time$/i.test(adminCaption.trim()), adminCaption.trim());

  // ---------------------------------------------------------------- stock health
  // `/analytics/inventory/` had been routed since Day 2 with a full, correctly
  // scoped implementation, **no test and no caller** — the third endpoint in this
  // project that existed only as an API. It is now on the dashboard, so it needs the
  // same treatment as any other panel.
  section('/ — the stock-health panel reports the real threshold');

  let invReady = false;
  try {
    await page.waitForSelector('[data-testid="inventory-panel"]', { timeout: 20000 });
    invReady = true;
  } catch { /* reported below */ }
  check('the dashboard has a stock-health panel', invReady,
    'no [data-testid=inventory-panel] appeared');

  const invText = invReady
    ? await page.locator('[data-testid="inventory-panel"]').innerText()
    : '';
  check('the panel states the threshold it is using',
    /below 10 units/i.test(invText), invText.slice(0, 200));
  check('and explains that out-of-stock is a subset of low',
    /out-of-stock items are also below the low threshold/i.test(invText),
    invText.slice(0, 200));

  // The seeded catalogue's lowest stock is 25, so the honest render here is the
  // empty state — and an empty state that explains itself is the assertion.
  const healthyState = await page.locator('[data-testid="inventory-all-healthy"]').count();
  const lowRows = await page.locator('[data-testid="low-stock-row"]').count();
  check('the panel shows either low rows or an explained empty state',
    healthyState > 0 || lowRows > 0,
    `healthy=${healthyState} rows=${lowRows}`);

  if (healthyState > 0) {
    check('the empty state says nothing needs restocking, not that it failed',
      /nothing (is below|to restock)/i.test(invText), invText.slice(0, 200));
    // Cross-check the claim against the endpoint: an empty panel must mean the API
    // really reported nothing, not that the render swallowed a payload.
    // `API` is the origin without `/api`, so the path is appended here.
    const invApi = await page.evaluate(async (api) => {
      const token = window.localStorage.getItem('admin_token');
      const res = await fetch(`${api}/api/analytics/inventory/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      return res.ok ? await res.json() : null;
    }, API);
    check('and the API agrees that nothing is below the threshold',
      invApi !== null && invApi.low_stock_count === 0,
      `API low_stock_count=${invApi && invApi.low_stock_count}`);
  }

  const vendorRevenue = parseRs(vendorRevenueText);
  check('the vendor revenue is readable', vendorRevenue !== null,
    `vendor stat text was ${JSON.stringify(vendorRevenueText)}`);
  check('the vendor and the admin do not see the same Total Revenue',
    vendorRevenue !== null && headline !== null && vendorRevenue !== headline,
    `vendor=${vendorRevenue} admin=${headline}`);
  check('the vendor sees less than the shop-wide total, never more',
    vendorRevenue !== null && headline !== null && vendorRevenue < headline,
    `vendor=${vendorRevenue} admin=${headline}`);

  await page.screenshot({ path: `${SHOTS}/shot_14_areas.png`, fullPage: true });

  // ---------------------------------------------------------------- orders
  section('/orders — a refused status change must not destroy the table');

  // `/orders` had no browser coverage at all, which is how a real defect survived: a
  // **failed status write** set the same `error` state the load failure uses, so one
  // rejected PATCH replaced the entire table with a block headed "Could not load
  // orders" — a message that was untrue (the list had loaded fine) that also destroyed
  // the list the admin was working through.
  //
  // The check works on a **scratch order it places itself**, so no seeded order's
  // status history is polluted. `purge_verification_orders` sweeps it afterwards.
  let scratchOrderId = null;
  if (customerToken) {
    const catalogue = await api('GET', '/api/products/?page=1');
    const product = catalogue.body?.results?.[0];
    const areas = await api('GET', '/api/products/areas/');
    const area = Array.isArray(areas.body) ? areas.body[0] : null;

    if (product && area) {
      await api('POST', '/api/orders/cart/add/', customerToken,
        { product_id: product.id, quantity: 1 });
      const placed = await api('POST', '/api/orders/checkout/', customerToken, {
        shipping_address: 'browser_check.mjs orders section',
        phone: '9800000001',
        shipping_city: area.slug,
        payment_method: 'cod',
        notes: 'Placed by browser_check.mjs — safe to delete',
      });
      scratchOrderId = placed.body?.id ?? null;
      check('a scratch order was placed for the orders screen',
        placed.status === 201 && scratchOrderId !== null,
        `status=${placed.status} body=${JSON.stringify(placed.body).slice(0, 120)}`);
    }
  }

  await page.goto(`${ADMIN}/orders`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.table tbody tr', { timeout: 20000 });

  const orderRows = await page.locator('.table tbody tr').count();
  check('the orders table renders rows', orderRows > 0, `rows=${orderRows}`);
  check('the orders page offers a status control per row',
    await page.locator('.status-select').count() === orderRows,
    `${await page.locator('.status-select').count()} selects for ${orderRows} rows`);

  await page.screenshot({ path: `${SHOTS}/shot_16_orders.png`, fullPage: true });

  // --- force the write to fail, deterministically, with a route intercept.
  // A 400 is used rather than a 403 so the API client surfaces the server's own
  // message rather than its generic permission text.
  await page.route('**/api/orders/admin/orders/*/', (route) => {
    if (route.request().method() === 'PATCH') {
      return route.fulfill({
        status: 400,
        contentType: 'application/json',
        body: JSON.stringify({ status: ['This status is not allowed right now.'] }),
      });
    }
    return route.continue();
  });

  const firstSelect = page.locator('.status-select').first();
  const originalStatus = await firstSelect.inputValue();
  const differentStatus = originalStatus === 'confirmed' ? 'processing' : 'confirmed';
  await firstSelect.selectOption(differentStatus);

  // Assert on the **error-styled notice**, not on a phrase from the server's message.
  // The first version of this check looked for "not allowed right now", which never
  // appears: the API client only lifts `detail` / `error` / `non_field_errors` out of a
  // DRF body, so a per-field error like `{"status": [...]}` falls back to its generic
  // "Request failed (400). Please try again." Asserting on a string the client never
  // produces is a check that cannot pass for the right reason.
  let refusedNotice = false;
  try {
    await page.waitForSelector('.notice-error', { timeout: 20000 });
    refusedNotice = true;
  } catch { refusedNotice = false; }
  check('a refused status change is reported to the user', refusedNotice,
    'no error-styled notice appeared after the PATCH was rejected');

  const refusalText = await page.locator('.notice-error').first().innerText().catch(() => '');
  check('the refusal message is the server\'s or the client\'s, not silence',
    refusalText.trim().length > 0, `notice text was ${JSON.stringify(refusalText)}`);

  // This is the assertion the bug would have failed. The table must survive.
  const tableStillThere = await page.locator('.table tbody tr').count() > 0;
  check('a refused status change does NOT replace the table', tableStillThere,
    'the order list was replaced — a write failure is being rendered as a load failure');

  const bodyAfterRefusal = await page.locator('body').innerText();
  check('the message does not claim the orders could not be loaded',
    !/could not load orders/i.test(bodyAfterRefusal),
    'the screen says it could not load the orders, which is untrue — they loaded');

  await page.screenshot({ path: `${SHOTS}/shot_17_order_refused.png`, fullPage: true });

  await page.unroute('**/api/orders/admin/orders/*/');

  // --- and the happy path still works, with a real success notice.
  await page.locator('.status-select').first().selectOption(differentStatus);
  let savedNotice = false;
  try {
    await page.waitForFunction(
      (s) => new RegExp(`updated to ${s}`, 'i').test(document.body.innerText),
      differentStatus, { timeout: 20000 },
    );
    savedNotice = true;
  } catch { savedNotice = false; }
  check('a successful status change is confirmed on screen', savedNotice,
    `no "updated to ${differentStatus}" message appeared`);

  // The refresh that follows a write is **silent**, so the table must never disappear
  // into skeletons for it. Asserted immediately, with no settling delay: a non-silent
  // refetch is what made this fail before, and a `waitForTimeout` here would have hidden
  // exactly the flicker the check exists to catch.
  const tableAfterSuccess = await page.locator('.table tbody tr').count() > 0;
  check('the table survives a successful change without blanking', tableAfterSuccess,
    'the table went to skeletons on a write-triggered refresh');

  if (scratchOrderId) {
    console.log(`  note  order ${scratchOrderId} left for purge_verification_orders`);
  }

  // ---------------------------------------------------------------- forecast
  section('/forecast — the model is labelled synthetic, and the horizon works');

  await page.goto(`${ADMIN}/forecast`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(3500);

  const forecastText = await page.locator('body').innerText();
  check('the forecast page renders its heading', /demand forecast/i.test(forecastText));

  // The most important assertion on this screen. The model is fitted on **generated**
  // data, and the project's rule is that it must never be presented as real demand — the
  // label is carried in three places precisely because dropping it would leave plausible
  // numbers reading as measured demand. A UI regression that lost this banner would be
  // invisible to every API test, which only checks the payload's own flags.
  check('the page states the forecast is synthetic, not real demand',
    /synthetic/i.test(forecastText) && /not real demand/i.test(forecastText),
    'the provenance banner is missing — the numbers now read as real demand');

  const forecastRows = await page.locator('.table tbody tr').count();
  check('the restock table renders rows', forecastRows > 0, `rows=${forecastRows}`);
  check('the page names the model and its version',
    /seasonal-trend-festival/i.test(forecastText), forecastText.slice(0, 160));

  const horizon = page.locator('#horizon');
  check('the horizon selector is offered', await horizon.count() === 1);
  await horizon.selectOption('7');
  let horizonApplied = false;
  try {
    await page.waitForFunction(
      () => /units over 7d/i.test(document.body.innerText), { timeout: 25000 },
    );
    horizonApplied = true;
  } catch { horizonApplied = false; }
  check('changing the horizon actually refetches at the new horizon', horizonApplied,
    'the "units over 7d" badge never appeared');

  const tableText = await page.locator('.table').last().innerText();
  check('each row reports a MAPE, or an explicit n/a',
    /\d+(\.\d+)?%|n\/a/i.test(tableText), tableText.slice(0, 120));

  await page.getByRole('button', { name: /^Why\?$/ }).first().click();
  let expanded = false;
  try {
    await page.waitForFunction(
      () => /model components/i.test(document.body.innerText), { timeout: 20000 },
    );
    expanded = true;
  } catch { expanded = false; }
  check('"Why?" explains the model components behind a row', expanded,
    'the explanation row never opened');

  await page.screenshot({ path: `${SHOTS}/shot_18_forecast.png`, fullPage: true });

  // ---------------------------------------------------------------- settings
  section('/settings — taxonomy and delivery areas are authorable');

  const settingsStamp = Date.now();

  await page.goto(`${ADMIN}/settings`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  check('the settings page renders its heading',
    /catalog settings/i.test(await page.locator('body').innerText()));
  check('both tabs are offered',
    await page.getByRole('button', { name: /^Categories$/ }).count() === 1
      && await page.getByRole('button', { name: /Delivery Areas/ }).count() === 1,
    'the Categories or Delivery Areas tab is missing');

  // --- categories: a full create → assert → delete round trip, on a row this run owns.
  await page.getByRole('button', { name: /^Categories$/ }).click();
  // Guarded, like every other wait in this file. An unguarded `waitForSelector` that
  // times out throws out of `main()` and takes the whole run down with it — no summary,
  // no list of what passed, nothing. One run of this very section did exactly that.
  // The `check` below is what should report the failure, not a stack trace.
  await page.waitForSelector('.table tbody tr', { timeout: 20000 }).catch(() => {});
  check('the categories table renders rows',
    await page.locator('.table tbody tr').count() > 0);

  const catName = `ZZ E2E Browser Cat ${settingsStamp}`;
  await page.getByRole('button', { name: /\+ New Category/i }).click();
  await page.waitForSelector('#c-name', { timeout: 20000 });
  await page.fill('#c-name', catName);
  await page.getByRole('button', { name: /^Save$/ }).click();

  let catCreated = false;
  try {
    await page.waitForFunction(
      (n) => document.body.innerText.includes(n), catName, { timeout: 25000 },
    );
    catCreated = true;
  } catch { catCreated = false; }
  check('a category can be created from the settings screen', catCreated,
    `"${catName}" never appeared in the table`);

  // Close the dialog if it is still open, whatever happened above. A failed save leaves
  // the modal up, and it then intercepts every later click — the first version of this
  // check died with a 30-second "subtree intercepts pointer events" timeout instead of
  // reporting the real problem.
  if (await page.locator('.modal').count() > 0) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
  }

  if (catCreated) {
    await page.getByRole('row', { name: new RegExp(catName) })
      .getByRole('button', { name: /^Delete$/ }).click();
    await page.locator('.modal button.btn-danger').click();
    let catGone = false;
    try {
      await page.waitForFunction(
        (n) => !document.body.innerText.includes(n), catName, { timeout: 25000 },
      );
      catGone = true;
    } catch { catGone = false; }
    check('the scratch category is deleted again', catGone,
      `${catName} was left behind — delete it from /settings`);
  }

  // --- delivery areas: the same round trip on the second tab.
  await page.getByRole('button', { name: /Delivery Areas/ }).click();
  // Switching tabs mounts `AreasPanel`, whose `useCrud` hook immediately calls
  // `load()` — so the panel renders three skeletons, not the table, until the fetch
  // returns. A bare `waitForTimeout` here is a bet on the network, and the row count
  // below is read on the other side of it. Wait for a row instead; that is the thing
  // the assertion is actually about. (Same race as the seeded-areas check below, and
  // the same cause: a skeleton state that looks exactly like "no rows".)
  await page.waitForSelector('.table tbody tr', { timeout: 20000 }).catch(() => {});
  check('the delivery areas table renders rows',
    await page.locator('.table tbody tr').count() > 0);

  const areaName = `ZZ E2E Browser Area ${settingsStamp}`;
  await page.getByRole('button', { name: /\+ New Area/i }).click();
  await page.waitForSelector('#a-name', { timeout: 20000 });
  await page.fill('#a-name', areaName);
  await page.fill('#a-district', 'Kathmandu');
  await page.getByRole('button', { name: /^Save$/ }).click();

  let areaCreated = false;
  try {
    await page.waitForFunction(
      (n) => document.body.innerText.includes(n), areaName, { timeout: 25000 },
    );
    areaCreated = true;
  } catch { areaCreated = false; }
  check('a delivery area can be created from the settings screen', areaCreated,
    `"${areaName}" never appeared in the table`);

  if (await page.locator('.modal').count() > 0) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
  }

  if (areaCreated) {
    await page.getByRole('row', { name: new RegExp(areaName) })
      .getByRole('button', { name: /^Delete$/ }).click();
    await page.locator('.modal button.btn-danger').click();
    let areaGone = false;
    try {
      await page.waitForFunction(
        (n) => !document.body.innerText.includes(n), areaName, { timeout: 25000 },
      );
      areaGone = true;
    } catch { areaGone = false; }
    check('the scratch area is deleted again', areaGone,
      `${areaName} was left behind — delete it from /settings`);
  }

  // The three seeded areas must be untouched by any of the above.
  //
  // **Wait for the table to come back before reading it.** Deleting the scratch row
  // calls `load()`, which sets `loading = true`; while that is true `AreasPanel`
  // renders three `.skeleton-line` divs *instead of* the table (settings/page.js:375).
  // The `waitForFunction` above only waits for the scratch *name* to disappear, and
  // that happens the instant the skeletons mount — i.e. before the refetch has
  // returned. Reading `body.innerText()` right there saw an empty panel and reported
  // "a seeded area went missing" while all three were sitting in the database.
  //
  // Measured at that exact instant: skeletonCount=3, tableRowCount=0, hasTable=false.
  // After waiting for a row: tableRowCount=3, all three names present. The assertion
  // was never testing the data — it was racing a skeleton, and it failed on 2 of 3
  // consecutive runs for a shop whose areas were correct throughout.
  await page.waitForSelector('.table tbody tr', { timeout: 20000 }).catch(() => {});

  const areasText = await page.locator('body').innerText();
  check('the three seeded delivery areas are still listed',
    ['Kathmandu', 'Lalitpur', 'Bhaktapur'].every((n) => areasText.includes(n)),
    'a seeded area went missing');

  // The same race, one line down: an empty or skeleton panel means the API has not
  // answered yet, so assert the row count too — a table that renders zero rows is a
  // different failure from a table that has not rendered, and the check above cannot
  // tell them apart on its own.
  const areaRowCount = await page.locator('.table tbody tr').count();
  check('the areas table is populated, not merely name-free',
    areaRowCount >= 3, `rows=${areaRowCount}`);

  await page.screenshot({ path: `${SHOTS}/shot_19_settings.png`, fullPage: true });

  // ---------------------------------------------------------------- image upload
  section('/products — an image can actually be uploaded');

  // A throwaway product, created and deleted by this run. Uploading over a *seeded*
  // product's picture would destroy real data and there is no way to put the original
  // back, so the check makes its own row instead — the same rule the storefront check
  // follows with its order and its review.
  const stamp = Date.now();
  const tempName = `Browser Check Image ${stamp}`;
  const tempPng = `${SHOTS}/browser_check_upload_${stamp}.png`;

  // A real 1x1 PNG on disk. `setInputFiles` needs a path, and the backend's
  // ImageField will reject anything that is not decodable — so a text file named
  // .png would fail the upload for the right reason but prove nothing.
  fs.writeFileSync(tempPng, Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
    'base64',
  ));

  await page.goto(`${ADMIN}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.table tbody tr', { timeout: 20000 });

  await page.getByRole('button', { name: /\+ New Product/i }).click();
  await page.waitForSelector('#p-name', { timeout: 15000 });

  check('the product dialog offers an image input', await page.isVisible('#image-input'),
    'no file input rendered — the upload widget is missing');

  await page.fill('#p-name', tempName);
  await page.fill('#p-desc', 'Created by the browser check to prove image upload works.');
  await page.fill('#p-price', '99');
  await page.fill('#p-stock', '3');
  await page.setInputFiles('#image-input', tempPng);

  // The preview is a blob URL from the picked file. If it renders, the file reached
  // the component; if the upload later fails, the two are distinguishable.
  let previewed = false;
  try {
    await page.waitForFunction(
      () => !!document.querySelector('#image-input')
        && !!document.querySelector('img[alt="Current image"]'),
      { timeout: 10000 },
    );
    previewed = true;
  } catch { previewed = false; }
  check('picking a file shows a preview before saving', previewed,
    'no preview image appeared');

  await page.getByRole('button', { name: /Create Product/i }).click();

  let created = false;
  try {
    await page.waitForFunction(
      () => /Product created\./i.test(document.body.innerText),
      { timeout: 25000 },
    );
    created = true;
  } catch { created = false; }
  check('saving a product with an image succeeds', created,
    'the create request did not report success — the multipart upload likely failed');

  await page.waitForTimeout(2000);

  // Asserted **unfiltered**, deliberately. The admin catalogue list is unpaginated
  // (it is a management list), and a new product sorts last by popularity — so this
  // check is the regression guard for a real defect: paginated at 12, a product
  // created through this very dialog fell onto the last page and never appeared, and
  // the "Total Products" card read 12 against 36 real rows. Filtering the table first
  // would hide that bug rather than catch it.
  const findRow = () => page.getByRole('row', { name: new RegExp(tempName) });
  let rowCount = await findRow().count();

  check('the new product appears in the unfiltered table', rowCount > 0,
    `matching rows=${rowCount} — the list may be hiding rows behind a page`);

  // If it is not there, fall back to the search box so the row can still be deleted
  // and this run does not leave data behind. A check that only cleans up on the happy
  // path leaves the mess from exactly the failures worth investigating.
  if (rowCount === 0) {
    await page.fill('.search-input', tempName);
    await page.waitForTimeout(1500);
    rowCount = await findRow().count();
    if (rowCount > 0) {
      console.log('  note  found the row only via search — cleaned up anyway');
    }
  }

  if (rowCount > 0) {
    // The thumbnail is what proves the *server* stored a file and returned a URL,
    // rather than the dialog merely keeping the local preview.
    const thumb = await findRow().first().locator('img').count();
    check('the new row renders the uploaded thumbnail', thumb > 0,
      'no <img> in the new row — the image did not persist');
  }

  await page.screenshot({ path: `${SHOTS}/shot_15_image_upload.png`, fullPage: true });

  // Read the **server-stored** URL before deleting the product.
  //
  // Deleting the row removes the DB record, and with it the only pointer to the file —
  // but Django does not delete the file itself. So every run of this section left one
  // `browser_check_upload_*.png` behind in `backend/media/products/`, forever. Thirteen
  // had accumulated by Day 15c, against a catalogue of 35 products: the check deleted
  // the product it owned and leaked the file it did not clean up.
  //
  // **The first version of this guard passed while the leak continued**, because the
  // URL was read through `.catch(() => null)`: when `getAttribute` threw, the value
  // silently became `null`, the whole unlink block was skipped, and no check was ever
  // reached. A guard that can vanish without saying so is worse than no guard. So the
  // capture is asserted in its own right, and the deletion is attempted regardless.
  let storedImageRel = null;
  if (rowCount > 0) {
    const srcAttr = await findRow().first().locator('img').first()
      .getAttribute('src').catch((e) => `__ERROR__:${e.message}`);
    if (typeof srcAttr === 'string' && srcAttr.includes('/media/')) {
      storedImageRel = srcAttr.replace(/^.*\/media\//, '');
    }
    check('the uploaded image URL was readable before the row was deleted',
      storedImageRel !== null,
      `src=${JSON.stringify(srcAttr)} — without this the file-leak guard cannot run`);
  }

  // Clean up: delete the throwaway product so the catalogue is left as it was found.
  if (rowCount > 0) {
    await findRow().first().getByRole('button', { name: /Delete/i }).click();
    const confirm = page.getByRole('button', { name: /^Delete$/i }).last();
    await confirm.click().catch(() => {});
    let gone = false;
    try {
      await page.waitForFunction(
        (nm) => !new RegExp(nm).test(document.body.innerText),
        tempName, { timeout: 20000 },
      );
      gone = true;
    } catch { gone = false; }
    check('the throwaway product is cleaned up again', gone,
      `${tempName} was left behind — delete it from /products`);

    // Unlink once the row is really gone, so a failed delete does not leave a product
    // pointing at a file that no longer exists — a broken thumbnail is worse than an
    // orphaned one. Runs whether or not the URL was readable: if the capture failed we
    // still know the name this harness's upload always uses, so fall back to it rather
    // than silently skipping the cleanup.
    if (gone) {
      // Remove by **prefix**, not just by the URL we read.
      //
      // Django's storage appends a random suffix when the target name already exists, so
      // a leftover `browser_check_upload.png` makes the *next* run store its file as
      // `browser_check_upload_vJPTswo.png`. The row's `src` then shows the suffixed name
      // while an earlier unsuffixed file is still lying around — measured directly:
      // the directory held `['browser_check_upload.png', 'browser_check_upload_vJPTswo.png']`
      // and deleting the one from `src` left the other. Every check reported PASS while
      // the directory kept growing.
      //
      // Sweeping the prefix is safe precisely because the prefix is ours: no seeded
      // asset can be named `browser_check_upload*`, and the name is the marker.
      const dir = path.join(MEDIA_ROOT, 'products');
      let removed = [];
      let fileRemoved = false;
      try {
        const stale = fs.existsSync(dir)
          ? fs.readdirSync(dir).filter((f) => f.startsWith('browser_check_upload'))
          : [];
        for (const f of stale) {
          fs.unlinkSync(path.join(dir, f));
          removed.push(f);
        }
        fileRemoved = true;
      } catch { fileRemoved = false; }
      check('the uploaded file does not leak into media/', fileRemoved,
        `could not clear ${path.join(dir, 'browser_check_upload*')}`);
      if (removed.length > 1) {
        console.log(`  note  swept ${removed.length} stale uploads: ${removed.join(', ')}`);
      }
    }
  } else {
    check('the throwaway product was cleaned up', false,
      `could not locate ${tempName} to delete it — remove it from /products`);
  }

  // ---------------------------------------------------------------- console
  section('No uncaught client errors on any page');

  // React's dev-mode noise and the favicon 404 are not component failures.
  //
  // The `/orders` section also provokes a **deliberate** 400 by intercepting the status
  // PATCH, so that the "a refused write must not destroy the table" assertion has a real
  // refusal to work with. It is matched narrowly — that one URL, that one method, that
  // one status — rather than by ignoring 400s, because a blanket "ignore 400" would hide
  // the next genuine failure and is how a guard ends up passing for the wrong reason.
  const expectedError = (e) =>
    /status of 400/i.test(e) && /\/orders\/admin\/orders\/\d+\//i.test(e);

  const realErrors = consoleErrors.filter(
    (e) => !/favicon|Download the React DevTools|net::ERR_/i.test(e)
      && !/status of 404/i.test(e)
      && !expectedError(e)
  );
  if (realErrors.length) console.log('  console errors seen:', realErrors.slice(0, 5));
  check('no uncaught exception or console error', realErrors.length === 0,
    realErrors.slice(0, 3).join(' || '));

  await browser.close();

  console.log(`\n${'='.repeat(60)}`);
  console.log(`  ${pass} passed, ${fail} failed`);
  if (failures.length) {
    console.log('  Failed checks:');
    for (const name of failures) console.log(`    - ${name}`);
  }
  console.log(`${'='.repeat(60)}`);
  return fail ? 1 : 0;
}

main().then((code) => process.exit(code)).catch((err) => {
  console.error('HARNESS ERROR:', err.message);
  process.exit(2);
});
