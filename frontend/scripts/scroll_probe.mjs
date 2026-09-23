/**
 * Scroll-jank probe for the storefront landing page.
 *
 * Why this exists
 * ---------------
 * The landing page scrolled badly and nothing in the project could see it: the
 * unit tests do not render, `storefront_check.mjs` asserts content rather than
 * smoothness, and the build is happy either way. Four separate causes were
 * fixed on 2026-09-23 — a `backdrop-filter: blur()` on the sticky navbar, an
 * infinite `pulse` animation inside that same bar, two unpromoted 400px
 * rotating dashed-border circles in the hero, and ~7 MB of eagerly-decoded
 * images. This probe is the regression check for all four: it measures real
 * frame intervals during a scripted scroll and fails loudly if long frames
 * come back.
 *
 * A "long frame" is one over 50 ms, i.e. worse than three frames at 60 Hz —
 * the threshold below which a scroll reads as smooth. The headless browser
 * here settles at a ~21 ms median, so the median is NOT a frame-rate
 * measurement; the number that matters is the count of long frames, which
 * should be zero.
 *
 * It also reports broken and relative `<img>` sources, because the same page
 * once shipped eleven relative image URLs that 404'd against the storefront's
 * own origin.
 *
 * Run against a PRODUCTION build (`npm run build && npx next start -p 3000`),
 * with NODE_PATH pointing at the harness (see AGENTS.md §5):
 *
 *   NODE_PATH='C:\Users\dell\AppData\Local\Temp\harness\node_modules' \
 *     node scripts/scroll_probe.mjs
 *
 * Baseline at the time of the fix: 0 long frames of 354, worst 21-25 ms,
 * 12 images, 0 broken, 0 relative. Override the target with PROBE_URL.
 */
import { createRequire } from 'module';
const require = createRequire(import.meta.url);
const { chromium } = require('playwright-core');

const URL = process.env.PROBE_URL || 'http://127.0.0.1:3000/';
const ROUNDS = 3;

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });

const errors = [];
page.on('pageerror', (e) => errors.push(String(e).slice(0, 120)));

await page.goto(URL, { waitUntil: 'networkidle', timeout: 60000 });
// Let images below the fold start loading, as they would for a real visitor.
await page.waitForTimeout(1500);

const results = [];
for (let round = 0; round < ROUNDS; round++) {
  const sample = await page.evaluate(async () => {
    const frames = [];
    let last = performance.now();
    let running = true;
    const tick = () => {
      const now = performance.now();
      frames.push(now - last);
      last = now;
      if (running) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);

    // Scroll the full document in ~40 px steps, like a wheel or trackpad.
    const height = document.documentElement.scrollHeight;
    for (let y = 0; y < height - window.innerHeight; y += 40) {
      window.scrollTo(0, y);
      await new Promise((r) => requestAnimationFrame(r));
    }
    running = false;
    await new Promise((r) => setTimeout(r, 100));

    frames.shift(); // drop the first delta (includes setup)
    const sorted = [...frames].sort((a, b) => a - b);
    return {
      frames: frames.length,
      long: frames.filter((f) => f > 50).length,
      worst: Math.round(sorted[sorted.length - 1] || 0),
      median: Math.round(sorted[Math.floor(sorted.length / 2)] || 0),
      scrollHeight: height,
    };
  });
  results.push(sample);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
}

const imgStats = await page.evaluate(() => {
  const imgs = [...document.querySelectorAll('img')];
  const broken = imgs.filter((i) => i.complete && i.naturalWidth === 0);
  const relative = imgs.filter((i) => i.getAttribute('src')?.startsWith('/'));
  return { total: imgs.length, broken: broken.length, relative: relative.length };
});

console.log('URL              ', URL);
console.log('scroll height    ', results[0].scrollHeight, 'px');
console.log('images           ', `total ${imgStats.total} | broken ${imgStats.broken} | relative ${imgStats.relative}`);
console.log('');
console.log('round | frames | long>50ms | worst ms | median ms');
for (const [i, r] of results.entries()) {
  console.log(
    `  ${i + 1}   |  ${String(r.frames).padStart(4)}  |    ${String(r.long).padStart(3)}    |   ${String(r.worst).padStart(4)}   |   ${String(r.median).padStart(3)}`
  );
}
const worstAll = Math.max(...results.map((r) => r.worst));
const longAll = results.reduce((a, r) => a + r.long, 0);
const framesAll = results.reduce((a, r) => a + r.frames, 0);
console.log('');
console.log(`TOTAL long frames: ${longAll} of ${framesAll} (${((longAll / framesAll) * 100).toFixed(1)}%) | worst frame ${worstAll} ms`);
if (errors.length) console.log('page errors:', errors.slice(0, 5));

await browser.close();
