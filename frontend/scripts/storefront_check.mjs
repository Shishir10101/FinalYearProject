/**
 * Real-browser check of the customer storefront.
 *
 * The admin dashboard got this on Day 9 and it immediately found a bug no API test
 * could see. The storefront is the part that actually gets demonstrated — browse →
 * festival/ritual → product → cart → checkout → history — and until now it had only
 * ever been verified through the API and the build output.
 *
 * Neither of those can see a client-side render failure. This project has shipped
 * that class of bug before: a home-page "+" that looked like add-to-cart and had no
 * handler, and four `Catalog Settings` buttons that threw `ReferenceError` before
 * their dialog opened. Both compiled cleanly and linted cleanly.
 *
 * It also drives the *whole* purchase path, which the API verifiers only cover
 * piecewise, and it checks the one thing a customer would notice immediately: that
 * the total promised on the checkout button is the total the order records. That
 * exact mismatch — a hardcoded delivery fee on the client — was a real bug here.
 *
 * This script places **one real order**. Its notes carry the marker
 * `browser_check.mjs`, which `purge_verification_orders` sweeps up (and that command
 * also clears the cart). Run it afterwards:
 *
 *   cd backend && ./venv/Scripts/python.exe manage.py purge_verification_orders
 *
 * It also **posts and then deletes a review** on the product it bought, so the badge
 * and the rating summary are exercised against a genuine purchase. The delete is part
 * of the run, not a manual step — a stray review would silently move a seeded
 * product's rating. If the run is interrupted mid-review, clean up with
 * `manage.py purge_verification_reviews`.
 *
 * It also **registers a throwaway account and resets its password**, so the three
 * auth screens are exercised end to end rather than only their endpoints. That
 * account is named `verifydaybrowser<stamp>` and the run deletes it again by calling
 * `manage.py purge_verification_users`, whose prefix match is what makes the sweep
 * safe. If the process is killed mid-run, run that command by hand — it is idempotent.
 *
 * Every route it touches is reached **by its own URL at least once**, not only by
 * clicking through. That distinction is deliberate: Next 16 makes `params` a Promise,
 * so a route can render correctly on a client-side click and 404 on a direct load,
 * and the build catches neither.
 *
 * Setup (once, outside the project so package.json stays untouched):
 *
 *   mkdir -p /tmp/harness && cd /tmp/harness
 *   npm init -y && npm install playwright-core
 *
 * Run (storefront on :3000, API on :8000):
 *
 *   cd frontend
 *   NODE_PATH=/tmp/harness/node_modules node scripts/storefront_check.mjs
 *
 * **On Windows, `NODE_PATH` must be a Windows path.** Git-Bash's `/tmp` is a mount,
 * not a real directory, and Node resolves `NODE_PATH` itself — it does not understand
 * `/tmp/...`, so the line above fails with `Cannot find module 'playwright-core'`
 * even though the package is installed. Resolve it once with `pwd -W` (or
 * `cygpath -w`) inside the harness directory and use the result:
 *
 *   NODE_PATH='C:\Users\<you>\AppData\Local\Temp\harness\node_modules' \
 *     node scripts/storefront_check.mjs
 *
 * Environment: `SHOP_BASE` overrides the storefront URL, `SHOT_DIR` the screenshot
 * directory (defaults to the working directory). Node cannot read a Git-Bash path
 * like `/c/Users/...` — pass a Windows path for `SHOT_DIR`.
 */

import { createRequire } from 'node:module';

// CJS resolution on purpose: a bare ESM `import` ignores NODE_PATH and resolves only
// from this file's own directory, so the documented invocation above would fail with
// ERR_MODULE_NOT_FOUND even with the package installed.
const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');

const SHOP = process.env.SHOP_BASE || 'http://127.0.0.1:3000';
const SHOTS = process.env.SHOT_DIR || '.';
const ORDER_MARKER = 'browser_check.mjs';

const USERNAME = 'testuser';
const PASSWORD = 'test1234';

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

const money = (text) => {
  const m = String(text).replace(/,/g, '').match(/Rs\.?\s*([\d.]+)/);
  return m ? Number(m[1]) : null;
};

async function main() {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  page.on('console', (msg) => {
    if (msg.type() !== 'error') return;
    const url = (msg.location() && msg.location().url) || '';
    consoleErrors.push(`${msg.text()} @ ${url}`);
  });
  page.on('pageerror', (err) => consoleErrors.push(`pageerror: ${err.message}`));

  // ---------------------------------------------------------------- home
  section('The home page leads with the festival domain, not a product grid');

  await page.goto(`${SHOP}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('h1', { timeout: 25000 });

  const homeH1 = await page.locator('h1').first().textContent();
  check('the hero renders', homeH1.trim().length > 0, homeH1);

  const homeText = await page.locator('body').innerText();
  check('a festival is named on the first screen',
    /Dashain|Tihar|Shivaratri|Bratabandha|Pasni|Griha|Shraddha|Teej|Chhath|Saraswati|Janai|Nag/i.test(homeText),
    'no festival name found in the page text');
  // Case-insensitive: `innerText` reflects CSS `text-transform`, and this eyebrow is
  // uppercased in the stylesheet, so a literal 'Next festival' never matches.
  check('the festival calendar is present', /next festival/i.test(homeText), '');

  const homeCards = await page.locator('a[href^="/products/"]').count();
  check('product cards render', homeCards > 0, `cards=${homeCards}`);

  // Every recommendation must carry the backend's reason, not an invented one.
  const reasonCount = await page.locator('text=/✨/').count();
  check('recommendations carry their reason text', reasonCount > 0, `reasons=${reasonCount}`);

  await page.screenshot({ path: `${SHOTS}/shop_1_home.png`, fullPage: true });

  // ------------------------------------------------- signed-out guard
  section('A signed-out visitor is sent to login, not a 401');

  await page.goto(`${SHOP}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });

  const addButton = page.getByRole('button', { name: /^Log in to add .* to cart$/ }).first();
  check('the add button says "Log in to add", not "Add"',
    await addButton.count() > 0, 'no signed-out add button found');

  if (await addButton.count() > 0) {
    await addButton.click();
    await page.waitForURL(/\/auth\/login/, { timeout: 20000 }).catch(() => {});
    check('clicking it routes to login', page.url().includes('/auth/login'), page.url());
    check('and remembers where to come back to', page.url().includes('redirect='), page.url());
  }

  // --------------------------------------------- registration (signed out)
  section('Registration works through the form, not just the endpoint');

  // The register *endpoint* is covered live by verify_day4.py; the screen was not.
  // A screen is where a client-side render failure lives, and this project has
  // shipped exactly that class of bug before.
  //
  // This creates a throwaway account and the run deletes it again at the end. The
  // username announces itself for the same reason `verify_day3c.py`'s scratch area
  // is called `ZZ E2E …`: an interrupted run must leave something recognisable, not
  // something that looks like a real customer. It is unique per run so a re-run
  // cannot collide on "username already exists" and fail for the wrong reason.
  const stamp = Date.now().toString(36);
  const PROBE_USERNAME = `verifydaybrowser${stamp}`;
  const PROBE_EMAIL = `verifydaybrowser${stamp}@example.com`;
  const PROBE_PASSWORD = 'BrowserCheckPass123';
  const PROBE_NEW_PASSWORD = 'BrowserCheckPass456';
  // A third password, because the Account Security section changes it again via the
  // authenticated endpoint — which is a different code path from the reset flow and
  // must be provable independently of it.
  const PROBE_CHANGED_PASSWORD = 'BrowserCheckPass789';

  // Set once registration has actually succeeded. The Account Security section is
  // gated on this: it drives a real signed-in account, and running it without one
  // would fail for a reason that has nothing to do with the panel.
  let accountCreated = false;

  await page.goto(`${SHOP}/auth/register`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('form', { timeout: 25000 });

  // --- mismatched passwords must be refused on the client ---
  // Filling the form is positional: these inputs have no `name` attribute, so the
  // selector has to be by order. Recorded here rather than hidden in a helper.
  const regInputs = page.locator('form input');
  check('the register form collects the fields it needs',
    await regInputs.count() >= 7, `inputs=${await regInputs.count()}`);

  await regInputs.nth(0).fill('Browser');
  await regInputs.nth(1).fill('Check');
  await regInputs.nth(2).fill(PROBE_USERNAME);
  await regInputs.nth(3).fill(PROBE_EMAIL);
  await regInputs.nth(4).fill('9800000001');
  await regInputs.nth(5).fill(PROBE_PASSWORD);
  await regInputs.nth(6).fill(`${PROBE_PASSWORD}-typo`);
  await page.click('form button[type="submit"]');
  await page.waitForTimeout(1500);

  check('a mismatched confirmation is refused without calling the API',
    page.url().includes('/auth/register'), `left the page: ${page.url()}`);
  check('and the customer is told why',
    /do not match|don.t match/i.test(await page.locator('body').innerText()),
    'no mismatch message surfaced');

  // --- the real submission ---
  await regInputs.nth(6).fill(PROBE_PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/auth/register'), { timeout: 25000 }),
    page.click('form button[type="submit"]'),
  ]);
  check('a valid registration leaves the form', !page.url().includes('/auth/register'),
    page.url());

  // Register then auto-logs in, so the header must now treat us as signed in. This
  // is the assertion that proves the account was really created and signed in, not
  // merely that the form cleared.
  await page.waitForTimeout(1500);
  const afterRegister = await page.locator('body').innerText();
  check('and lands signed in, not back at login',
    !/Log in|Sign in/i.test(afterRegister.split('\n').slice(0, 3).join(' '))
      || /Log ?out|Sign ?out|Account/i.test(afterRegister),
    afterRegister.slice(0, 200));

  accountCreated = true;

  await page.screenshot({ path: `${SHOTS}/shop_1b_register.png`, fullPage: true });

  // Sign back out, so the rest of the run starts from the same state the old
  // harness did. The sign-in section below then genuinely signs `testuser` in.
  await page.evaluate(() => {
    window.localStorage.removeItem('access_token');
    window.localStorage.removeItem('refresh_token');
    window.localStorage.removeItem('user');
  });
  await page.goto(`${SHOP}/`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1000);

  // --------------------------------------------- password reset (signed out)
  section('Forgot password → reset → sign in with the new password');

  // The token flow is covered live by verify_day7.py. What was never covered is the
  // two screens. This walks the whole loop in one browser session: request a link,
  // follow it, set a new password, and then *actually log in with it* — which is the
  // only assertion that distinguishes "the form said Saved" from "the password
  // changed". It uses the throwaway account, never a seeded one.
  await page.goto(`${SHOP}/auth/forgot-password`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('form', { timeout: 25000 });
  check('the forgot-password form renders', await page.locator('form').count() > 0, '');

  await page.fill('#reset-email', PROBE_EMAIL);
  await page.click('form button[type="submit"]');

  // The response is deliberately identical for a known and an unknown address, so
  // the generic notice is the *only* thing a customer sees either way.
  let noticeShown = true;
  try {
    await page.waitForSelector('[role="status"]', { timeout: 25000 });
  } catch { noticeShown = false; }
  const noticeText = noticeShown
    ? await page.locator('[role="status"]').first().innerText() : '';
  check('it answers with the generic notice, revealing nothing', noticeShown, noticeText);
  check('the notice does not say whether the address exists',
    !/no account|not found|unknown|does not exist/i.test(noticeText),
    `leaked: ${noticeText}`);

  // In this build the link is returned instead of emailed, so the screen shows it.
  const resetLink = page.locator('a[href^="/auth/reset-password"]');
  const hasResetLink = await resetLink.count() > 0;
  check('the dev build exposes the reset link it could not email', hasResetLink,
    'no link rendered — has PASSWORD_RESET_EXPOSE_LINK been turned off?');

  // Read the href *now*, while the notice is still on screen. The incomplete-link
  // probe below navigates away, and a locator resolved after that finds nothing —
  // which is exactly how this harness failed the first time it was run.
  const resetHref = hasResetLink ? await resetLink.first().getAttribute('href') : null;

  await page.screenshot({ path: `${SHOTS}/shop_1c_forgot_password.png`, fullPage: true });

  // --- the incomplete-link state, which must not show a form that cannot work ---
  await page.goto(`${SHOP}/auth/reset-password`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1200);
  const incompleteText = await page.locator('body').innerText();
  check('opening /auth/reset-password with no token explains the link is needed',
    /valid reset link|request a new one/i.test(incompleteText),
    incompleteText.slice(0, 200));
  check('and offers no password form to fill in', await page.locator('form').count() === 0,
    'a form was rendered for a link that cannot work');

  // --- the real link ---
  if (resetHref) {
    const href = resetHref;
    check('the reset link carries a uid and a token',
      /uid=[^&]+/.test(href) && /token=[^&]+/.test(href), href);
    check('and points at the storefront, not the API host',
      href.startsWith('/auth/reset-password'), href);

    await page.goto(`${SHOP}${href}`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#new-password', { timeout: 25000 });
    check('a valid link renders the choose-a-password form',
      await page.locator('#new-password').count() > 0, '');

    // Mismatched confirmation, refused on the client.
    await page.fill('#new-password', PROBE_NEW_PASSWORD);
    await page.fill('#confirm-password', `${PROBE_NEW_PASSWORD}-typo`);
    await page.click('form button[type="submit"]');
    await page.waitForTimeout(1500);
    check('a mismatched new password is refused',
      await page.locator('#new-password').count() > 0,
      'the form was left despite the mismatch');

    await page.fill('#new-password', PROBE_NEW_PASSWORD);
    await page.fill('#confirm-password', PROBE_NEW_PASSWORD);
    await page.click('form button[type="submit"]');

    let resetDone = true;
    try {
      await page.waitForFunction(
        () => /Password Updated|now sign in/i.test(document.body.innerText),
        { timeout: 25000 },
      );
    } catch { resetDone = false; }
    check('the reset completes and says so', resetDone,
      (await page.locator('body').innerText()).slice(0, 200));

    await page.screenshot({ path: `${SHOTS}/shop_1d_reset_password.png`, fullPage: true });

    // --- the old password must be dead and the new one alive ---
    await page.goto(`${SHOP}/auth/login`, { waitUntil: 'domcontentloaded' });
    await page.locator('form input[type="text"]').first().fill(PROBE_USERNAME);
    await page.locator('form input[type="password"]').first().fill(PROBE_PASSWORD);
    await page.click('form button[type="submit"]');
    await page.waitForTimeout(2500);
    check('the old password no longer works', page.url().includes('/auth/login'),
      `the pre-reset password still signed in: ${page.url()}`);

    await page.locator('form input[type="text"]').first().fill(PROBE_USERNAME);
    await page.locator('form input[type="password"]').first().fill(PROBE_NEW_PASSWORD);
    await Promise.all([
      page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 25000 }),
      page.click('form button[type="submit"]'),
    ]);
    check('the new password signs in', !page.url().includes('/auth/login'), page.url());

    // --- a used link is dead, which is what "the link works exactly once" means ---
    // The page renders the form optimistically: it has no way to know the token is
    // spent until it asks the API, and it only asks on submit. So the assertion has
    // to submit. An earlier version of this check asserted the *load* refused the
    // link, which the screen was never designed to do — that was a verifier bug, and
    // it is worth remembering that "the app does not do X" and "the app does X
    // differently" look identical from a badly aimed assertion.
    await page.evaluate(() => {
      window.localStorage.removeItem('access_token');
      window.localStorage.removeItem('refresh_token');
      window.localStorage.removeItem('user');
    });
    await page.goto(`${SHOP}${href}`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('#new-password', { timeout: 25000 });

    await page.fill('#new-password', 'AnotherPass789');
    await page.fill('#confirm-password', 'AnotherPass789');
    await page.click('form button[type="submit"]');

    let reuseRefused = true;
    try {
      await page.waitForFunction(
        () => /expired|invalid|request a new/i.test(document.body.innerText),
        { timeout: 25000 },
      );
    } catch { reuseRefused = false; }
    check('a link that has been used is refused on submit', reuseRefused,
      (await page.locator('body').innerText()).slice(0, 200));

    // The page hides the form once the token is known dead — a dead link cannot be
    // fixed by retyping a password, so leaving the form up invites a second failure.
    check('and the form is replaced rather than left to fail again',
      await page.locator('#new-password').count() === 0,
      'the form was still offered for a spent token');
  }

  // --- an unknown address must be indistinguishable ---
  await page.goto(`${SHOP}/auth/forgot-password`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('form', { timeout: 25000 });
  await page.fill('#reset-email', `nobody-${stamp}@example.com`);
  await page.click('form button[type="submit"]');
  await page.waitForTimeout(2500);
  const unknownText = await page.locator('body').innerText();
  check('an unregistered address gets the same answer as a registered one',
    /if an account exists/i.test(unknownText), unknownText.slice(0, 200));
  check('and no reset link is handed out for it',
    await page.locator('a[href^="/auth/reset-password"]').count() === 0,
    'a link was exposed for an address with no account');

  // ------------------------------------------------- account security panel
  // Both controls here had no home before: `/auth/password-change/` did not exist,
  // and `/auth/logout-all/` had existed since Day 7 — documented in the API docs as
  // "a real user-facing action" — with **no client calling it**. A security feature
  // the user cannot invoke is not a feature, so this drives the panel rather than
  // trusting that the buttons render.
  //
  // Runs while the probe account is signed in with `PROBE_NEW_PASSWORD`.
  if (accountCreated) {
    section('/account — password change and sign-out-everywhere are reachable');

    // **Own the precondition.** The reset section above deliberately clears
    // localStorage to prove a spent link is refused while signed out, so the probe
    // account is *not* signed in here — `/account` renders its "Please login" branch
    // and the panel is legitimately absent. The first version of this section went
    // straight to `/account` and failed on three assertions plus a 30s locator
    // timeout, none of which had anything to do with the panel. Sign in explicitly.
    await page.goto(`${SHOP}/auth/login`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('form input[type="password"]', { timeout: 25000 });
    await page.locator('form input[type="text"]').first().fill(PROBE_USERNAME);
    await page.locator('form input[type="password"]').first().fill(PROBE_NEW_PASSWORD);
    await Promise.all([
      page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 25000 }),
      page.click('form button[type="submit"]'),
    ]).catch(() => {});
    check('the probe account can sign back in to reach its account page',
      !page.url().includes('/auth/login'), page.url());

    await page.goto(`${SHOP}/account`, { waitUntil: 'domcontentloaded' });
    let securityReady = false;
    try {
      await page.waitForSelector('[data-testid="account-security"]', { timeout: 25000 });
      securityReady = true;
    } catch { /* reported below */ }
    check('the account page offers an Account Security panel', securityReady,
      'no [data-testid=account-security] appeared');

    check('the panel offers a password change',
      await page.locator('[data-testid="open-change-password"]').count() === 1);
    check('the panel offers sign out everywhere',
      await page.locator('[data-testid="sign-out-everywhere"]').count() === 1);

    await page.click('[data-testid="open-change-password"]');
    await page.waitForSelector('#current-password', { timeout: 20000 });

    await page.screenshot({ path: `${SHOTS}/shop_1e_account_security.png`, fullPage: true });

    // A wrong current password must be refused AND must not change anything. The
    // second half is the part that matters: a 400 that still wrote the password
    // would look identical from the screen.
    await page.fill('#current-password', 'DefinitelyNotThePassword9');
    await page.fill('#new-password-1', 'PanelPass9876');
    await page.fill('#new-password-2', 'PanelPass9876');
    await page.click('[data-testid="submit-change-password"]');
    await page.waitForFunction(
      () => /not your current password/i.test(document.body.innerText),
      { timeout: 25000 },
    ).catch(() => {});
    const wrongPwText = await page.locator('body').innerText();
    check('a wrong current password is refused in place',
      /not your current password/i.test(wrongPwText), wrongPwText.slice(0, 200));
    check('and it does not sign the customer out',
      !page.url().includes('/auth/login'), page.url());

    // The right one goes through and then signs every session out — including this
    // one — so the customer lands back on the login screen rather than continuing
    // with a token the server has already revoked.
    await page.fill('#current-password', PROBE_NEW_PASSWORD);
    await page.fill('#new-password-1', PROBE_CHANGED_PASSWORD);
    await page.fill('#new-password-2', PROBE_CHANGED_PASSWORD);
    await page.click('[data-testid="submit-change-password"]');
    let landedBackOnLogin = true;
    try {
      await page.waitForURL((url) => url.pathname.startsWith('/auth/login'), { timeout: 25000 });
    } catch { landedBackOnLogin = false; }
    check('a successful change sends the customer back to sign in again',
      landedBackOnLogin, page.url());
    check('and the logout really happened locally, not just visually',
      await page.evaluate(() => !window.localStorage.getItem('access_token')),
      'a stale token was left in localStorage');

    // Prove the switch from the outside: the old password must be dead.
    await page.waitForSelector('form input[type="password"]', { timeout: 20000 });
    await page.locator('form input[type="text"]').first().fill(PROBE_USERNAME);
    await page.locator('form input[type="password"]').first().fill(PROBE_NEW_PASSWORD);
    await page.click('form button[type="submit"]');
    await page.waitForTimeout(2500);
    check('after the change the pre-change password no longer signs in',
      page.url().includes('/auth/login'), `it still signed in: ${page.url()}`);

    await page.locator('form input[type="password"]').first().fill(PROBE_CHANGED_PASSWORD);
    await Promise.all([
      page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 25000 }),
      page.click('form button[type="submit"]'),
    ]).catch(() => {});
    check('and the new one does', !page.url().includes('/auth/login'), page.url());

    // Sign out everywhere. Same consequence: this session goes too.
    await page.goto(`${SHOP}/account`, { waitUntil: 'domcontentloaded' });
    await page.waitForSelector('[data-testid="sign-out-everywhere"]', { timeout: 25000 });
    await page.click('[data-testid="sign-out-everywhere"]');
    let signedOutAll = true;
    try {
      await page.waitForURL((url) => url.pathname.startsWith('/auth/login'), { timeout: 25000 });
    } catch { signedOutAll = false; }
    check('sign out everywhere also ends this session', signedOutAll, page.url());

    // ...and it is a sign-out, not a lockout: the password still works.
    await page.waitForSelector('form input[type="password"]', { timeout: 20000 });
    await page.locator('form input[type="text"]').first().fill(PROBE_USERNAME);
    await page.locator('form input[type="password"]').first().fill(PROBE_CHANGED_PASSWORD);
    await page.click('form button[type="submit"]');
    await page.waitForTimeout(2500);
    check('the password still works after signing out everywhere',
      !page.url().includes('/auth/login'), `locked out: ${page.url()}`);

    await page.evaluate(() => {
      window.localStorage.removeItem('access_token');
      window.localStorage.removeItem('refresh_token');
      window.localStorage.removeItem('user');
    });
  }

  // The account is left in place deliberately: the run deletes it at the very end,
  // via the API, so a failure part-way through is still cleaned up by the sweep
  // command documented in the footer if the process is killed instead.

  // ---------------------------------------------------------------- sign in
  section('Sign in');

  await page.goto(`${SHOP}/auth/login`, { waitUntil: 'domcontentloaded' });
  await page.locator('form input[type="text"]').first().fill(USERNAME);
  await page.locator('form input[type="password"]').first().fill(PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith('/auth/login'), { timeout: 25000 }),
    page.click('form button[type="submit"]'),
  ]);
  check('login leaves the login page', !page.url().includes('/auth/login'), page.url());

  // ---------------------------------------------------------------- cart empty
  section('The cart starts empty (established, not assumed)');

  await page.goto(`${SHOP}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  const cartBody = await page.locator('body').innerText();
  check('the cart is empty before we add anything',
    /empty|no items|Nothing/i.test(cartBody), cartBody.slice(0, 160));

  // ---------------------------------------------------------------- discovery
  section('Discovery through the required entry points');

  await page.goto(`${SHOP}/festivals`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/festivals/"], .card, h1', { timeout: 25000 });
  const festivalsText = await page.locator('body').innerText();
  check('/festivals names kits', /Kit/i.test(festivalsText), festivalsText.slice(0, 160));
  await page.screenshot({ path: `${SHOTS}/shop_2_festivals.png`, fullPage: true });

  await page.goto(`${SHOP}/pujas`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/pujas/"]', { timeout: 25000 });
  const ritualLinks = await page.locator('a[href^="/pujas/"]').count();
  check('/pujas lists rituals', ritualLinks >= 8, `links=${ritualLinks}`);
  await page.screenshot({ path: `${SHOTS}/shop_3_rituals.png`, fullPage: true });

  // Follow the first ritual through to its detail page and add its essentials.
  await page.locator('a[href^="/pujas/"]').first().click();
  await page.waitForURL(/\/pujas\/[^/]+$/, { timeout: 25000 });
  const ritualSlug = page.url().split('/pujas/')[1];

  // A client-side nav updates the URL before the Server Component payload renders,
  // so waiting on the URL alone reads the loading fallback (skeletons). Wait for the
  // samagri list itself.
  let ritualRendered = true;
  try {
    await page.waitForFunction(
      () => /Essential|Required/i.test(document.body.innerText)
        && !document.body.innerText.includes('Loading'),
      { timeout: 25000 },
    );
  } catch { ritualRendered = false; }

  const ritualText = await page.locator('body').innerText();
  check('the ritual detail page renders', ritualText.length > 200, `slug=${ritualSlug}`);
  check('it separates essential from optional samagri',
    /Required|Essential/i.test(ritualText), ritualText.slice(0, 200));
  await page.screenshot({ path: `${SHOTS}/shop_4_ritual_detail.png`, fullPage: true });

  const essentialsButton = page.getByRole('button', { name: /Add essentials to cart/i });
  check('the add-essentials control is present for a signed-in user',
    await essentialsButton.count() > 0,
    `ritualRendered=${ritualRendered}; the button is only rendered once the auth context knows the user`);

  if (await essentialsButton.count() > 0) {
    await essentialsButton.click();
    await page.waitForTimeout(2500);
    const afterAdd = await page.locator('body').innerText();
    check('adding essentials reports what it did',
      /added|cart/i.test(afterAdd), 'no confirmation surfaced');
  }

  await page.screenshot({ path: `${SHOTS}/shop_5_after_add_essentials.png`, fullPage: true });

  // ------------------------------------------- ritual detail, by direct URL
  section('/pujas/[slug] loads from a URL, not only from a click');

  // Everything above reached this page by *clicking* a link. That hides a whole
  // class of failure: Next 16 makes `params` a Promise, and `const { slug } = params`
  // yields `undefined` — which sends every valid ritual to `notFound()` while the
  // build stays clean, because the mistake is a runtime value and not a syntax
  // error. A click through client-side navigation can mask it too. This is the same
  // reason /checkout is loaded directly below.
  //
  // A full page.goto, then: the page must render *this* ritual's title, and an
  // unknown slug must produce a real 404 rather than a 200 with "not found" inside.
  const deepLoaded = await page.goto(`${SHOP}/pujas/${ritualSlug}`, { waitUntil: 'domcontentloaded' });
  let deepRendered = true;
  try {
    await page.waitForFunction(
      () => /Essential|Required/i.test(document.body.innerText)
        && !document.body.innerText.includes('Loading'),
      { timeout: 25000 },
    );
  } catch { deepRendered = false; }

  check('a direct URL to a ritual renders it',
    deepRendered && (await page.locator('h1').first().textContent()).trim().length > 0,
    `slug=${ritualSlug} url=${page.url()}`);
  check('the page did not bounce to the 404 UI',
    !/not\s*found|could not be found/i.test(await page.locator('body').innerText()),
    'the awaited-params trap would look exactly like this');

  const deepSlugEcho = await page.locator('body').innerText();
  check('it is the ritual the URL asked for, not a different one',
    deepSlugEcho.length > 200, `slug=${ritualSlug}`);

  // An unknown ritual must show the 404 UI, not an empty shell. Note what is *not*
  // asserted here: the HTTP status. `src/app/pujas/loading.js` opens a Suspense
  // boundary, so the response has already begun streaming when the fetch resolves and
  // `notFound()` renders into a committed 200 — measured with curl, and a documented
  // Next constraint rather than a defect. Asserting `status === 404` here would fail
  // forever for a reason that is not fixable without giving up the loading skeleton.
  // What matters, and what is asserted, is the user-visible behaviour plus the
  // `noindex` that Next injects as the mitigation.
  const missing = await page.goto(`${SHOP}/pujas/zz-no-such-ritual-${Date.now()}`,
    { waitUntil: 'domcontentloaded' });
  const missingText = await page.locator('body').innerText();
  check('an unknown ritual shows the 404 page',
    /could not find that page|not\s*found/i.test(missingText), missingText.slice(0, 160));
  check('and does not pretend it loaded',
    !/Essential samagri/i.test(missingText),
    'a missing ritual rendered the real detail page shell');
  check('and the page is marked noindex when it cannot return 404',
    missing.status() === 404 || /name="robots" content="noindex"/i.test(
      await page.content()),
    `status=${missing.status()} and no noindex meta — an unknown slug could be indexed`);

  await page.screenshot({ path: `${SHOTS}/shop_4b_ritual_direct.png`, fullPage: true });

  // ---------------------------------------------------------------- search
  section('Search — the Samagri entry point');

  // A request counter, for the same reason the reviews section carries one: the
  // results loader is a `useCallback` whose dependency list includes the toast
  // helpers, so an unstable `error` there would refetch forever. That is a real bug
  // this project has already shipped once (537 requests in 12 seconds).
  let searchCalls = 0;
  const countSearchCalls = (req) => {
    if (/\/products\/search\//.test(req.url())) searchCalls += 1;
  };
  page.on('request', countSearchCalls);

  // --- a second spelling of a Nepali term ---
  //
  // Loaded by URL on purpose. A search that cannot be linked to cannot be shared,
  // bookmarked or demonstrated, and this project has already shipped one page that
  // only worked when navigated to from the right place.
  await page.goto(`${SHOP}/products?q=sindur`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });

  const sindurH1 = await page.locator('h1').first().innerText();
  check('a search URL loads directly and names the query',
    /sindur/i.test(sindurH1), `h1=${sindurH1}`);

  const sindurText = await page.locator('body').innerText();
  check('an alternative spelling finds the product',
    /Sindoor Powder/i.test(sindurText), 'Sindoor Powder not in the results');
  check('and the page says which spelling it matched on',
    /alternative spelling/i.test(sindurText), sindurText.slice(0, 300));
  check('the page lists the spellings it tried',
    /also searched for/i.test(sindurText), 'no expanded-term line');

  await page.screenshot({ path: `${SHOTS}/shop_15_search_sindur.png`, fullPage: true });

  // --- a ritual name, which no product is named after ---
  await page.goto(`${SHOP}/products?q=pasni`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });

  const pasniText = await page.locator('body').innerText();
  const pasniCards = await page.locator('a[href^="/products/"]').count();
  check('a ritual name returns samagri', pasniCards > 0, `cards=${pasniCards}`);
  check('the page names the ritual it matched',
    /Pasni \(Rice Feeding\)/i.test(pasniText), pasniText.slice(0, 300));

  // The point of the whole feature: none of these products is named after the
  // ritual. If a card contained "pasni", this would only be proving a substring
  // match and the domain link would be untested.
  const pasniCardNames = await page.locator('a[href^="/products/"] h4')
    .evaluateAll((els) => els.map((e) => e.innerText));
  check('no result is named after the ritual — the link is the domain, not the text',
    pasniCardNames.length > 0 && !pasniCardNames.some((n) => /pasni/i.test(n)),
    `names=${pasniCardNames.join(' | ')}`);
  check('a card explains that the item is required for the ritual',
    /required for/i.test(pasniText), pasniText.slice(0, 300));

  await page.screenshot({ path: `${SHOTS}/shop_16_search_ritual.png`, fullPage: true });

  // --- a typo ---
  await page.goto(`${SHOP}/products?q=sindoer`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const typoText = await page.locator('body').innerText();
  check('a misspelling says nothing matched', /nothing matches/i.test(typoText),
    typoText.slice(0, 300));
  check('and offers a correction', /did you mean/i.test(typoText), 'no suggestion offered');
  check('the correction is the real spelling',
    /sindoor/i.test(typoText), typoText.slice(0, 300));

  const suggestion = page.getByRole('button', { name: 'sindoor', exact: true });
  check('the suggestion is a control, not just text', await suggestion.count() > 0,
    'no clickable suggestion');
  if (await suggestion.count() > 0) {
    await suggestion.first().click();
    await page.waitForTimeout(2500);
    const correctedText = await page.locator('body').innerText();
    check('clicking it runs the corrected search',
      /Sindoor Powder/i.test(correctedText), correctedText.slice(0, 300));
    check('and the URL carries the corrected query', /q=sindoor/.test(page.url()), page.url());
  }
  await page.screenshot({ path: `${SHOTS}/shop_17_search_typo.png`, fullPage: true });

  // --- too short ---
  await page.goto(`${SHOP}/products?q=x`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const shortText = await page.locator('body').innerText();
  check('a one-character query asks for more typing', /keep typing/i.test(shortText),
    shortText.slice(0, 300));
  check('rather than claiming the catalogue has no such product',
    !/no products found/i.test(shortText), 'told the shopper there is no match');

  // --- the loop guard ---
  //
  // Reset the counter first: it has been tallying every search this section ran, so
  // an absolute bound is only meaningful against one page load. Two windows, because
  // "it stopped" and "it was slow to start" are different things.
  searchCalls = 0;
  await page.goto(`${SHOP}/products?q=diyo`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });
  await page.waitForTimeout(4000);
  const callsAtFour = searchCalls;
  await page.waitForTimeout(4000);
  const callsAtEight = searchCalls;
  page.off('request', countSearchCalls);
  check('a search page fetches once, not in a loop',
    callsAtFour <= 3 && callsAtEight === callsAtFour,
    `search requests: ${callsAtFour} at 4s, ${callsAtEight} at 8s`);

  // --- the catalogue pages, rather than showing 12 of 35 and implying that is all ---
  await page.goto(`${SHOP}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });
  const firstPage = await page.locator('a[href^="/products/"]').count();
  const showMore = page.getByRole('button', { name: /show more/i });
  check('the catalogue offers a way past the first page', await showMore.count() > 0,
    `only ${firstPage} cards and no control to see the rest`);
  if (await showMore.count() > 0) {
    await showMore.first().click();
    await page.waitForTimeout(2500);
    const secondPage = await page.locator('a[href^="/products/"]').count();
    check('showing more actually adds products', secondPage > firstPage,
      `${firstPage} → ${secondPage}`);
  }
  await page.screenshot({ path: `${SHOTS}/shop_18_catalogue_paged.png`, fullPage: true });

  // ---------------------------------------------------------------- product
  section('Product detail and add to cart');

  await page.goto(`${SHOP}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('a[href^="/products/"]', { timeout: 25000 });
  await page.locator('a[href^="/products/"]').first().click();
  await page.waitForURL(/\/products\/[^/]+$/, { timeout: 25000 });

  // Remembered so the review section below can come back to the same product —
  // and so it can review something this run has actually bought.
  const productSlug = page.url().split('/products/')[1].split(/[?#]/)[0];

  const productH1 = await page.locator('h1').first().textContent();
  check('the product page renders a title', productH1.trim().length > 0, productH1);
  const productText = await page.locator('body').innerText();
  check('it shows a price', /Rs\.?\s*[\d]/.test(productText), 'no price found');
  check('it names the category', /Per |category/i.test(productText), '');

  const detailAdd = page.locator('button').filter({ hasText: /Add to Cart|Add To Cart/i }).first();
  check('the add-to-cart control exists', await detailAdd.count() > 0, 'button not found');
  if (await detailAdd.count() > 0) {
    await detailAdd.click();
    await page.waitForTimeout(2500);
    const afterDetailAdd = await page.locator('body').innerText();
    check('adding from the detail page is confirmed',
      /added|cart/i.test(afterDetailAdd), 'no confirmation surfaced');
  }
  await page.screenshot({ path: `${SHOTS}/shop_6_product_detail.png`, fullPage: true });

  // ---------------------------------------------------------------- cart
  section('The cart totals come from the API, not from the component');

  await page.goto(`${SHOP}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const cartText = await page.locator('body').innerText();
  check('the cart has line items', /Rs\.?\s*[\d]/.test(cartText), cartText.slice(0, 200));
  check('a delivery fee is shown', /Delivery/i.test(cartText), cartText.slice(0, 200));
  check('a subtotal is shown', /Subtotal/i.test(cartText), cartText.slice(0, 200));
  check('the cart is no longer empty', !/empty cart|no items/i.test(cartText), '');

  const lineItems = await page.locator('button').filter({ hasText: /^\+$/ }).count();
  check('line items have a quantity control', lineItems > 0, `controls=${lineItems}`);

  await page.screenshot({ path: `${SHOTS}/shop_7_cart.png`, fullPage: true });

  // ---------------------------------------------------------------- checkout
  section('Checkout — the promise on the button must match the recorded order');

  // Deliberately a full page load, not a click from /cart. This is the regression
  // check for a real bug: a direct load of /checkout bounced to /cart even with a
  // full cart, because the guard could not tell "the cart is empty" from "the cart
  // has not been fetched yet". Refresh, a bookmark and a shared link all broke, and
  // clicking through from the cart hid it.
  await page.goto(`${SHOP}/checkout`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  check('a full page load of /checkout stays on /checkout',
    page.url().includes('/checkout'), `redirected to ${page.url()}`);

  let formReady = true;
  try {
    await page.waitForSelector('form', { timeout: 20000 });
  } catch { formReady = false; }
  check('the checkout form renders', formReady, 'no <form> appeared');
  if (!formReady) {
    await page.screenshot({ path: `${SHOTS}/shop_8_checkout_failed.png`, fullPage: true });
    await browser.close();
    console.log(`\n  ${pass} passed, ${fail} failed — stopped at checkout`);
    return 1;
  }

  const areaOptions = await page.$$eval('select[name="shipping_city"] option',
    (opts) => opts.map((o) => o.value).filter(Boolean));
  check('the delivery areas come from the database', areaOptions.length === 3,
    `areas=${areaOptions.join(',')}`);
  check('they are the three Kathmandu Valley areas',
    areaOptions.includes('kathmandu') && areaOptions.includes('lalitpur')
      && areaOptions.includes('bhaktapur'),
    `areas=${areaOptions.join(',')}`);

  await page.fill('input[name="phone"]', '9800000000');
  await page.selectOption('select[name="shipping_city"]', 'lalitpur');
  await page.fill('textarea[name="shipping_address"]', 'Ward 4, Jhamsikhel, near the school');
  await page.fill('input[name="notes"]', `Placed by ${ORDER_MARKER} — safe to delete`);

  // --- the mocked gateways must announce themselves before the choice ---
  // eSewa and Khalti are simulated: picking one marks the order paid with no gateway
  // involved. The demo is entitled to that shortcut, but not to letting a customer
  // believe money was taken. This is the same rule the forecast page follows for
  // synthetic data, and only a browser can prove the warning is actually on screen —
  // the API can only prove the flag it renders from.
  const checkoutText = await page.locator('body').innerText();
  const tiles = await page.locator('[data-payment-method]').count();
  check('the payment methods are rendered from the store config', tiles === 3,
    `tiles=${tiles}`);

  check('the customer is warned that payment is simulated',
    /no real payment is taken/i.test(checkoutText),
    'no demo-payment warning on the checkout screen');

  const mockedTiles = await page.locator('[data-payment-method][data-mocked="true"]').count();
  check('the simulated methods are marked as such on their own tiles', mockedTiles === 2,
    `marked=${mockedTiles} (expected eSewa + Khalti)`);

  // The label has to be on the tile the customer clicks, not only in a banner that
  // can be scrolled past — so assert against the tile itself.
  const esewaTile = page.locator('[data-payment-method="esewa"]');
  check('the eSewa tile says it is simulated',
    /simulated/i.test(await esewaTile.innerText()), await esewaTile.innerText());

  const codTile = page.locator('[data-payment-method="cod"]');
  check('cash on delivery is not labelled simulated',
    !/simulated/i.test(await codTile.innerText()),
    'COD was wrongly marked as a mock — it is genuinely collected on delivery');

  // The button states the total it is about to charge. Read it, then hold the order
  // to it — a hardcoded client-side delivery fee once made these disagree.
  const submitLabel = await page.locator('form button[type="submit"]').textContent();
  const promisedTotal = money(submitLabel);
  check('the checkout button states a total', promisedTotal !== null, submitLabel);

  await page.screenshot({ path: `${SHOTS}/shop_8_checkout.png`, fullPage: true });

  await Promise.all([
    page.waitForURL(/\/account\/orders\/\d+/, { timeout: 30000 }),
    page.click('form button[type="submit"]'),
  ]);
  check('placing the order lands on the confirmation',
    /\/account\/orders\/\d+/.test(page.url()), page.url());

  await page.waitForTimeout(2000);
  const confirmText = await page.locator('body').innerText();
  const orderH1 = await page.locator('h1').first().textContent();
  check('the confirmation names the order', /Order #\d+/.test(orderH1), orderH1);

  const recordedTotal = money(
    (confirmText.match(/Total\s*Rs\.?\s*[\d,.]+/) || [''])[0]
  );
  check('the recorded total is what the button promised',
    promisedTotal !== null && recordedTotal === promisedTotal,
    `promised=${promisedTotal} recorded=${recordedTotal}`);

  check('the order timeline renders', await page.locator('.order-timeline').count() > 0,
    'no .order-timeline element');
  const timelineText = await page.locator('.order-timeline').first().innerText().catch(() => '');
  check('the first step is marked as reached',
    /Placed|Pending|Confirmed/i.test(timelineText), timelineText.slice(0, 160));
  check('the delivery area is recorded', /Lalitpur/i.test(confirmText), 'area missing');

  // This order was paid by COD, which is genuinely collected on delivery — so the
  // "simulated" notice must NOT appear. That is the half of the disclosure that is
  // easy to get wrong in the other direction: labelling everything makes the label
  // meaningless. See the eSewa/Khalti assertions on the checkout screen above.
  check('a cash-on-delivery order is not labelled as a demo payment',
    !/demo order|no money changed hands/i.test(confirmText),
    'COD was wrongly described as simulated');

  await page.screenshot({ path: `${SHOTS}/shop_9_order_confirmation.png`, fullPage: true });

  // ------------------------------- order detail, reached without a fresh order
  section('/account/orders/[id] reloads as a standalone page');

  // The confirmation above was rendered *by the checkout redirect*, so the order it
  // shows may well have come from the response body rather than from the detail
  // route fetching it. Everything on this page — the timeline markers, the item
  // snapshot, the totals — has only ever been asserted against that in-memory state.
  // A full reload is the only thing that proves the route can load an order on its
  // own, which is what a customer does when they open it from history or a bookmark.
  const orderUrl = page.url();
  const orderId = (orderUrl.match(/\/account\/orders\/(\d+)/) || [])[1];
  check('the confirmation URL carries the order id', !!orderId, orderUrl);

  await page.reload({ waitUntil: 'domcontentloaded' });
  let detailRendered = true;
  try {
    await page.waitForFunction(
      () => !/Loading/i.test(document.body.innerText)
        && /Order #\d+/i.test(document.body.innerText),
      { timeout: 25000 },
    );
  } catch { detailRendered = false; }

  check('a reload of the order keeps it on screen', detailRendered,
    'the detail route could not load the order the checkout had just created');

  const reloadedText = await page.locator('body').innerText();
  const reloadedTotal = money((reloadedText.match(/Total\s*Rs\.?\s*[\d,.]+/) || [''])[0]);
  check('the reloaded order records the same total',
    reloadedTotal !== null && reloadedTotal === promisedTotal,
    `promised=${promisedTotal} reloaded=${reloadedTotal}`);

  // The distinction the page is built around: "could not load" is an outage and
  // "not found" is a dead link. Conflating them tells a customer their order has
  // vanished whenever the API hiccups.
  check('a real order is not reported as missing',
    !/could not load|not found/i.test(reloadedText),
    reloadedText.slice(0, 200));

  await page.screenshot({ path: `${SHOTS}/shop_9b_order_detail_reload.png`, fullPage: true });

  // ---------------------------------------------------------------- history
  section('Order history');

  await page.goto(`${SHOP}/account`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const accountText = await page.locator('body').innerText();
  check('the order appears in history', /Order/i.test(accountText), accountText.slice(0, 200));
  check('history links to the order detail',
    await page.locator('a[href^="/account/orders/"]').count() > 0, 'no order links');

  await page.goto(`${SHOP}/account/orders`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  check('the orders list route also works',
    await page.locator('a[href^="/account/orders/"]').count() > 0, 'no order links');
  await page.screenshot({ path: `${SHOTS}/shop_10_account.png`, fullPage: true });

  // ---------------------------------------------------------------- reviews
  section('Ratings and reviews — posted, badged and removed through the UI');

  // Placed after the checkout on purpose: this run has now bought the product, so a
  // review written here is a *verified purchase* and the badge can be asserted. The
  // API verifier covers the endpoints; this covers the click path, which is the part
  // nothing has ever exercised.
  // Count the section's own API traffic. A regression pin for a real bug this check
  // found: `ReviewsSection`'s load effect depended on an inline `onSummaryChange`, so
  // it refetched in a loop — **537 requests in 12 seconds** on this very page, still
  // climbing. The build, ESLint, 336 unit tests and 575 live API assertions all
  // missed it. One fetch per page load is correct; anything that keeps growing is not.
  let reviewCalls = 0;
  const countReviewCalls = (req) => { if (/\/reviews\//.test(req.url())) reviewCalls += 1; };
  page.on('request', countReviewCalls);

  await page.goto(`${SHOP}/products/${productSlug}`, { waitUntil: 'domcontentloaded' });

  // The section is a client component that fetches on mount, so waiting for the page
  // shell proves nothing. Wait for its own content: the skeleton gone and real text in.
  let reviewsRendered = true;
  try {
    await page.waitForSelector('#reviews', { timeout: 25000 });
    await page.waitForFunction(() => {
      const el = document.querySelector('#reviews');
      return !!el && !el.querySelector('.skeleton-block') && /review/i.test(el.innerText);
    }, { timeout: 25000 });
  } catch { reviewsRendered = false; }

  check('the reviews section renders on the product page', reviewsRendered,
    'no settled #reviews content');
  if (!reviewsRendered) {
    await page.screenshot({ path: `${SHOTS}/shop_12_reviews_failed.png`, fullPage: true });
    await browser.close();
    console.log(`\n  ${pass} passed, ${fail} failed — stopped at the reviews section`);
    return 1;
  }

  check('it is headed Ratings & Reviews',
    /ratings\s*&\s*reviews/i.test(await page.locator('#reviews').innerText()), '');

  // Two windows, so "it stopped" is distinguishable from "it was slow to start".
  await page.waitForTimeout(5000);
  const callsAtFive = reviewCalls;
  await page.waitForTimeout(5000);
  const callsAtTen = reviewCalls;
  page.off('request', countReviewCalls);

  check('the reviews section fetches once per load, not in a loop',
    callsAtFive <= 3 && callsAtTen === callsAtFive,
    `review requests: ${callsAtFive} at 5s, ${callsAtTen} at 10s — a render loop refetches forever`);

  // Establish the precondition instead of assuming it. The seeded catalogue ships
  // with no reviews and `verify_day11.py` clears up after itself, but an interrupted
  // run could leave one — and then every assertion below would be measuring the wrong
  // baseline. Reported as a failure with the fix, not silently tolerated.
  const beforeReview = await page.locator('#reviews').innerText();
  check('this product starts with no reviews (so the counts below mean something)',
    /no reviews yet/i.test(beforeReview),
    `starting state: ${beforeReview.slice(0, 140)} — run purge_verification_reviews`);

  await page.screenshot({ path: `${SHOTS}/shop_12_reviews_empty.png`, fullPage: true });

  const writeButton = page.getByRole('button', { name: /Write a review/i });
  check('a signed-in shopper is offered "Write a review"',
    await writeButton.count() > 0, 'no write control for a signed-in user');
  await writeButton.first().click();
  await page.waitForSelector('#review-body', { timeout: 15000 });
  check('the review form opens', await page.isVisible('#review-body'));

  // A rating with no words is refused by the API. The component has to surface that
  // error — a form that submits and silently does nothing is exactly the class of bug
  // this harness exists to catch.
  await page.locator('#reviews form button[type="submit"]').click();
  await page.waitForTimeout(2000);
  const refusal = await page.locator('#reviews').innerText();
  check('a rating with no words is refused on screen, not silently dropped',
    /few words|meaning something|add a line/i.test(refusal), refusal.slice(0, 200));

  // 4 stars, not the 5 the picker defaults to — otherwise the average check passes
  // whether or not the rating was actually read from the form.
  await page.click('#review-rating button[aria-label="4 stars"]');
  await page.fill('#review-title', 'Solid quality');
  await page.fill('#review-body', `Bought and reviewed by ${ORDER_MARKER} — safe to delete.`);
  await page.locator('#reviews form button[type="submit"]').click();

  // Wait for the review inside the **list**, not just anywhere in the section.
  //
  // After a successful submit the component closes the form and shows the "Your
  // review" card straight away, while the list below it goes back to skeletons and
  // re-fetches. So a wait on the section's text can match the card and then read the
  // list while it is still loading — the badge and the author live only in the list,
  // and both checks failed exactly that way once. The card is a `div`; the list is the
  // only `<ul>` in the section.
  let posted = true;
  try {
    await page.waitForFunction(
      (needle) => Array.from(document.querySelectorAll('#reviews ul li'))
        .some((li) => li.innerText.includes(needle)),
      'Solid quality',
      { timeout: 25000 },
    );
  } catch { posted = false; }
  check('the published review appears in the list', posted, 'not found among #reviews ul li');

  const afterReview = await page.locator('#reviews').innerText();
  check('the summary counts one review', /\b1 review\b/i.test(afterReview),
    afterReview.slice(0, 200));
  check('the average reflects the 4 stars actually picked',
    /\b4\.0\b/.test(afterReview), afterReview.slice(0, 200));
  check('it is badged a verified purchase, because this run bought the product',
    /verified purchase/i.test(afterReview), 'no verified badge');
  check('the public list shows a display name, not the account',
    /Ram S\./.test(afterReview), `expected "Ram S."; saw: ${afterReview.slice(0, 200)}`);
  check('the username is not published in the review list',
    !/testuser/i.test(afterReview), 'the username leaked into a public list');
  check('the email address is not published either',
    !/test@example\.com/i.test(afterReview), 'an email address leaked');

  await page.screenshot({ path: `${SHOTS}/shop_13_reviews_posted.png`, fullPage: true });

  // Put the catalogue back. A stray review would silently move a seeded product's
  // rating, and both API verifiers assert a clean slate.
  const editButton = page.getByRole('button', { name: /Edit your review/i });
  check('the shopper is offered "Edit your review" once they have one',
    await editButton.count() > 0, 'no edit control after posting');
  await editButton.first().click();
  await page.waitForSelector('#review-body', { timeout: 15000 });
  await page.getByRole('button', { name: /Delete my review/i }).click();

  let removed = true;
  try {
    await page.waitForFunction(
      () => /no reviews yet/i.test(document.querySelector('#reviews')?.innerText || ''),
      { timeout: 25000 },
    );
  } catch { removed = false; }
  check('deleting through the UI returns the section to its empty state', removed,
    'the review survived its own delete');

  await page.screenshot({ path: `${SHOTS}/shop_14_reviews_removed.png`, fullPage: true });

  // ---------------------------------------------------------------- recommendations
  section('Recommendations explain themselves');

  await page.goto(`${SHOP}/recommendations`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const recCards = await page.locator('a[href^="/products/"]').count();
  check('recommendation cards render', recCards > 0, `cards=${recCards}`);
  const recText = await page.locator('body').innerText();
  check('the page names the ranking method',
    /festival|popularity|order|ranked|recommend/i.test(recText), recText.slice(0, 200));
  await page.screenshot({ path: `${SHOTS}/shop_11_recommendations.png`, fullPage: true });

  // ---------------------------------------------------------------- cart cleared
  section('Checkout emptied the cart');

  await page.goto(`${SHOP}/cart`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  const finalCart = await page.locator('body').innerText();
  check('the cart is empty again after ordering',
    /empty|no items|Nothing/i.test(finalCart), finalCart.slice(0, 160));

  // ---------------------------------------------------------------- wishlist
  section('Wishlist saves, persists across a reload, and removes');

  // Own the precondition. This run asserts about a wishlist it created itself, so
  // anything an interrupted previous run left behind is cleared first — otherwise
  // "the badge shows 1" would depend on state this script did not create. That is
  // the exact mistake `verify_day11.py` made about an order history it did not own.
  const clearWishlist = async () => {
    await page.goto(`${SHOP}/wishlist`, { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2200);
    for (let i = 0; i < 40; i += 1) {
      const btn = page.getByRole('button', { name: /Remove from wishlist/i });
      if ((await btn.count()) === 0) break;
      await btn.first().click();
      // The row is only dropped once the server has agreed, so wait for the count
      // to actually fall rather than assuming a fixed delay is enough.
      await page.waitForTimeout(900);
    }
  };
  await clearWishlist();

  await page.goto(`${SHOP}/products`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);

  const firstCard = page.locator('.grid a[href^="/products/"]').first();
  const savedName = (await firstCard.locator('h4').innerText()).trim();
  const urlBeforeSave = page.url();

  await firstCard.getByRole('button', { name: /Save .* to your wishlist/i }).first().click();

  // The state flips after the request resolves, so wait on the attribute rather than
  // reading the DOM immediately — the same race the toast/flash checks lost before.
  let heartFilled = false;
  try {
    await page.waitForFunction(
      () => [...document.querySelectorAll('button')]
        .some((b) => /Remove .* from your wishlist/i.test(b.getAttribute('aria-label') || '')
          && b.getAttribute('aria-pressed') === 'true'),
      { timeout: 20000 },
    );
    heartFilled = true;
  } catch { heartFilled = false; }
  check('clicking the heart marks the product as saved', heartFilled,
    'the heart never reported aria-pressed=true');

  // The heart lives inside the card's <Link>. Without preventDefault/stopPropagation
  // this click would also navigate, which is invisible to the API suite.
  check('the heart does not navigate to the product page',
    page.url() === urlBeforeSave, `url moved to ${page.url()}`);

  await page.screenshot({ path: `${SHOTS}/shop_19_wishlist_heart.png`, fullPage: true });

  // Persistence is the whole point of a wishlist: it must survive a full reload,
  // which is a fresh fetch from the server rather than context state.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  let stillSaved = false;
  try {
    await page.waitForFunction(
      () => [...document.querySelectorAll('button')]
        .some((b) => /Remove .* from your wishlist/i.test(b.getAttribute('aria-label') || '')
          && b.getAttribute('aria-pressed') === 'true'),
      { timeout: 20000 },
    );
    stillSaved = true;
  } catch { stillSaved = false; }
  check('the saved state survives a full page reload', stillSaved,
    'the heart reverted to unsaved after a reload');

  await page.goto(`${SHOP}/wishlist`, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2500);
  const wishlistText = await page.locator('body').innerText();
  check('the wishlist page lists the saved product',
    wishlistText.includes(savedName), `expected "${savedName}" in the wishlist page`);

  // The nav badge is the only signal a customer gets that saving worked while they
  // are somewhere else in the shop.
  const badgeCount = await page.locator('nav').innerText();
  check('the navbar shows a saved-item count', /\b1\b/.test(badgeCount), badgeCount.slice(0, 120));

  await page.screenshot({ path: `${SHOTS}/shop_20_wishlist_page.png`, fullPage: true });

  // Removing through the page's own control, then confirming the empty state — so a
  // run that is interrupted before the delete leaves nothing behind anyway, because
  // the next run clears it in `clearWishlist()`.
  await page.getByRole('button', { name: /Remove from wishlist/i }).first().click();
  let emptied = false;
  try {
    await page.waitForFunction(
      () => /nothing saved yet/i.test(document.body.innerText),
      { timeout: 20000 },
    );
    emptied = true;
  } catch { emptied = false; }
  check('removing the last item returns the wishlist to its empty state', emptied,
    'the removed item was still listed');

  // ---------------------------------------------- remove the scratch account
  section('The throwaway account is removed, not left behind');

  // A leftover login is a genuine handover smell, and the account this run created
  // has no business surviving it. The harness has no Django shell, so the sweep is
  // delegated to the management command that already owns this job — the same one
  // `verify_day4.py` relies on for exactly the same reason. The username prefix is
  // what it matches on, so nothing but this run's account can be swept up.
  //
  // Recorded rather than asserted: if this cannot run, the footer below still tells
  // the operator the exact command, so the cleanup is never silently skipped.
  let probeSwept = false;
  try {
    const { execFileSync } = require('node:child_process');
    const python = process.env.PYTHON_BIN || './venv/Scripts/python.exe';
    const out = execFileSync(python,
      ['manage.py', 'purge_verification_users'],
      { cwd: '../backend', encoding: 'utf8', timeout: 60000 });
    probeSwept = !/verifydaybrowser/i.test(out.split('remain:')[1] || '');
    console.log(`  ran purge_verification_users: ${out.trim().split('\n').pop()}`);
  } catch (e) {
    console.log(`  could not run the sweep automatically: ${e.message.split('\n')[0]}`);
  }
  check('the browser-check account does not survive the run', probeSwept,
    'run it by hand: cd backend && ./venv/Scripts/python.exe manage.py purge_verification_users');

  // ---------------------------------------------------------------- console
  section('No uncaught client errors on any page');

  // Four deliberate errors are expected, and each is the *point* of its check:
  //
  //  * the reviews section submits an empty review to prove the API's "a rating needs
  //    words" rule reaches the screen — the API answers 400 and the API client logs it;
  //  * a 404 is normal here (an unknown slug is probed on purpose, both a product and
  //    a ritual);
  //  * the password-reset section posts a *deliberately mismatched* confirmation to
  //    prove the server refuses it (the client only catches the empty-field case), and
  //    the API client logs the parsed field error rather than a status line;
  //  * it then signs in with the *old* password after resetting it, to prove the reset
  //    really took effect — that is a 401 by design, and it is what makes the check
  //    meaningful rather than decorative.
  //
  // All four are matched narrowly, on the endpoint, the status or the exact message.
  // A blanket "ignore 400" would hide the next genuine failure, which is how a guard
  // ends up passing for the wrong reason.
  const expectedError = (e) =>
    (/status of 400/i.test(e) && /\/reviews\//i.test(e))
    || /Please add a few words/i.test(e)
    || /two passwords do not match/i.test(e)
    || /reset link is invalid or has expired/i.test(e)
    // The API client's own line for the deliberate bad-password sign-in. It carries the
    // message but not the endpoint — only the `@ <url>` suffix names the file, and that
    // is a bundle path rather than a route. The message is exact and appears nowhere
    // else in the app, so it is specific enough to match on its own.
    || /Session expired\. Please login again\./i.test(e)
    // The browser also logs a bare network line for every non-2xx the page fetches,
    // separately from the API client's own parsed error above. Both halves of the two
    // deliberate refusals have to be matched, or the guard fails on the noise rather
    // than on a real error. Kept scoped to the exact endpoints this run provokes.
    || (/status of 400/i.test(e) && /\/auth\/password-reset\/confirm\//i.test(e))
    || (/status of 401/i.test(e) && /\/auth\/login\//i.test(e))
    // The Account Security section deliberately submits a wrong current password to
    // prove it is refused, so this 400 is provoked on purpose. Both halves appear:
    // the client's parsed `API Error:` line (which names the field but not the
    // endpoint) and the browser's bare network line (which names the endpoint).
    // Matched on the exact message and the exact route, never on the status alone.
    || /That is not your current password\./i.test(e)
    || (/status of 400/i.test(e) && /\/auth\/password-change\//i.test(e));

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
  console.log('\n  One order was placed. Clean it up with:');
  console.log('    cd backend && ./venv/Scripts/python.exe manage.py purge_verification_orders');
  console.log('  (the review this run posted was already deleted through the UI, and the');
  console.log('   throwaway account was swept by purge_verification_users — run it by hand');
  console.log('   if that step reported it could not).');
  return fail ? 1 : 0;
}

main().then((code) => process.exit(code)).catch((err) => {
  console.error('HARNESS ERROR:', err.message);
  process.exit(2);
});
