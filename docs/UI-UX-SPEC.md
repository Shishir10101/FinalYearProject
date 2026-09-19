# UI/UX Specification

The design system is **not invented here** — it already exists in
`frontend/src/app/globals.css` (~645 lines) and `admin-dashboard/src/app/globals.css`.
This document records it, states the rules, and names the gaps.

**Read those files before writing any style.** This document tells you what is
there and what may not be broken; the CSS is the authority.

---

## 1. Identity

A Nepali devotional aesthetic, not a generic SaaS look. Warm cream backgrounds,
deep crimson primary, gold accents — the palette of a puja shop rather than a
fintech dashboard.

### Tokens (`:root` in `frontend/src/app/globals.css`)

```css
/* Cultural palette */
--primary:          #C41E3A;   /* deep crimson — the brand */
--primary-dark:     #9B1830;
--primary-light:    #E8435A;
--secondary:        #D4A843;   /* temple gold */
--secondary-dark:   #B8902E;
--secondary-light:  #E8C76B;
--accent:           #FF6B35;   /* marigold orange */
--accent-light:     #FF8A5C;

/* Warm neutrals — note: NOT grey. Every surface has warmth. */
--bg-primary:       #FFF8F0;
--bg-secondary:     #FFF1E6;
--bg-card:          #FFFFFF;
--bg-dark:          #1A1A2E;

--text-primary:     #1A1A2E;
--text-secondary:   #4A4A6A;
--text-muted:       #8A8AAA;
--text-light:       #FFFFFF;

/* Status */
--success:  #2D6A4F   --success-light: #D4EDDA
--warning:  #F0AD4E   --warning-light: #FFF3CD
--danger:   #DC3545   --danger-light:  #F8D7DA
--info:     #17A2B8
```

**Spacing scale:** `--space-xs` 0.25rem → `--space-3xl` 4rem
**Radii:** `--radius-sm` 6px, `--radius-md`, …

### Typography

| Role | Family | Weights |
|---|---|---|
| Headings | **Outfit** | 400–800 |
| Body | **Inter** | 300–700 |

Loaded from Google Fonts via `@import` at the top of `globals.css`.
Headings use Outfit — a geometric face with more character than Inter and a
better fit for a cultural brand.

---

## 2. Non-negotiable rules

1. **Use tokens, never literals.** `var(--primary)`, not `#C41E3A`. The one
   documented exception is the pulse shadow (`rgba(196, 30, 58, 0.15)`), which
   needs alpha and has no token.
2. **Never introduce a UI kit or Tailwind.** The system is CSS Modules +
   custom properties. Adding a dependency would invalidate every existing style.
3. **Every async surface has four states.** Loading · success · empty · error.
   No blank screens, no silent failures.
4. **Never show a stack trace.** The API clients extract `.detail`, `.error`, or
   `.non_field_errors[0]` and show a human sentence. Raw exceptions go to the
   server log only.
5. **Distinguish "not found" from "load failed".** *"Order not found"* and
   *"Could not load this order"* are different messages for different causes.
   Collapsing them tells the customer the wrong thing. This was a real bug fixed
   on Day 3.
6. **Respect `prefers-reduced-motion`.** Any new animation must be disabled there.
7. **Mobile-first responsive.** Breakpoints at 640px and 900px.

---

## 3. The four-state vocabulary

| State | Treatment | Class |
|---|---|---|
| **Loading** | Skeleton shimmer, shaped like the content it replaces | `.skeleton-block`, `.skeleton-line` |
| **Success** | Toast (transient) or inline notice (persistent) | `.notice-success` |
| **Empty** | Icon + title + explanation + a call to action | `.empty-state` |
| **Error** | Icon + plain-language cause + a **Try again** button | `.empty-state` + `.notice-error` |

**Why skeletons, not spinners.** A skeleton communicates the shape of what is
coming, so the layout does not jump when data arrives. Spinners do not.

**Empty states always offer a next step.** "No orders yet" is followed by a link
to start shopping. An empty state that only reports absence is a dead end.

---

## 4. Animation

Deliberately sparse and purposeful. Nothing animates for decoration.

| Animation | Duration | Where | Purpose |
|---|---|---|---|
| `fadeInUp` | ~0.4s | product cards, sections | Staggered content entry |
| `fadeIn` | ~0.3s | modal backdrop | Context shift |
| `slideInRight` | ~0.3s | toasts | Non-blocking feedback |
| `pulse` | ~2s loop | stock/urgency badges | Draws the eye to time pressure |
| `shimmer` | ~1.4s loop | skeletons | Signals "loading", not "broken" |
| `pulse-marker` | ~2s loop | order timeline current step | "This is where you are" |
| `modal-in` | ~0.18s | admin modals | Spatial continuity |

**Rules:**
- Only **one** element animates at a time per region. Competing animations read as a bug.
- Looping animations are reserved for genuinely ongoing states (loading, current step).
- All of the above are disabled under `prefers-reduced-motion: reduce`.

---

## 5. Order status timeline *(added Day 3)*

The customer-facing tracker. Horizontal on desktop, vertical under 640px.

```
✓ Order Placed ──● Confirmed ──○ Preparing ──○ Out for Delivery ──○ Delivered
  (done)           (current)     (upcoming)
```

| State | Marker | Meaning |
|---|---|---|
| `done` | green filled, ✓ | Completed |
| `current` | crimson filled, pulse ring | Where the order is now |
| `upcoming` | warm grey, outlined | Not yet reached |
| `cancelled` | red filled, × | Terminal — replaces the whole progression |

**Design decisions:**
- **Cancelled is not a step on the line.** It is a different outcome, so it
  renders as its own 2-step timeline. Forcing it into step 6 of 5 would be dishonest.
- **Delivered is `done`, not `current`.** A finished order must not pulse. (This
  was a bug: the last step stayed `current` forever, so a completed order looked
  permanently in progress.)
- **Progress is derived from `status`.** The timeline cannot show *when* each step
  happened, because nothing records those timestamps. See `docs/DATABASE-DESIGN.md`
  for the proposed `OrderStatusEvent` table.

---

## 6. Role-aware UI

| Element | customer | vendor | admin / super |
|---|---|---|---|
| Sidebar: Festival Kits | — | hidden | shown |
| Sidebar: Catalog Settings | — | hidden | shown |
| Sidebar: Demand Forecast | — | shown (scoped) | shown |
| Product form: Vendor picker | — | read-only "Your shop" | full dropdown |
| `/settings` | — | explanatory panel | full CRUD |

**Hiding is a courtesy, not a boundary.** Every hidden screen is also enforced
server-side. A vendor who types `/settings` gets an explanatory panel — never a
broken-looking empty table.

---

## 7. Layout conventions

### Customer frontend

```
┌────────────────────────────────────────┐
│ Navbar (logo · nav · cart · account)   │
├────────────────────────────────────────┤
│ .container .section                    │  max-width, generous vertical rhythm
│                                        │
│   ┌──────────┐  ┌──────────┐           │  .grid.grid-2 / .grid-4
│   │  .card   │  │  .card   │           │
│   └──────────┘  └──────────┘           │
│                                        │
├────────────────────────────────────────┤
│ Footer                                 │
└────────────────────────────────────────┘
```

### Admin dashboard

Fixed sidebar (navigation + role badge + logout) with a scrolling content area.
Tables for lists, cards for KPIs and alerts, modals for editing.

---

## 8. Component inventory

| Component | Location | Used for |
|---|---|---|
| `ProductCard` | `frontend/src/components/ProductCard.js` | **Every** product tile — home, catalogue, recommendations |
| `Modal` | `admin-dashboard/src/components/Modal.js` | All create/edit dialogs |
| `ConfirmDialog` | `admin-dashboard/src/components/ConfirmDialog.js` | Every destructive action |
| `Badge` | `.badge` + variants | Status pills |
| `Notice` | `.notice` + variants | Inline success/error |
| `EmptyState` | `.empty-state` | Empty + error states |
| `Skeleton` | `.skeleton-block` / `.skeleton-line` | Loading |
| `StatusTimeline` | inline in order detail page | Order tracking |
| `Sparkline` | inline in forecast page | Forecast trend |
| `Toast` | `frontend/src/context/ToastContext` | Transient feedback |

**Accessibility:** modals set `role="dialog"` and `aria-modal`, close on `Escape`
and backdrop click, lock body scroll, and label their close button. Search inputs
carry `aria-label`. Icons that convey meaning are paired with text, and decorative
ones (the placeholder lamp, the reason sparkle) are `aria-hidden`.

### `ProductCard` — the single product tile
There used to be three implementations and they had drifted: the home version
omitted the unit, used a different category class, and its `+` button **had no
handler at all** — it looked like an add-to-cart control and did nothing. One
component now serves home, catalogue and recommendations.

It is a **client** component because the add button needs the cart context. It
reads that context itself rather than accepting a callback, so the Server
Component home page can render it without passing a function across the boundary.

| Prop | Effect |
|---|---|
| `product` | Required. `in_stock` drives whether the button is enabled |
| `reason` | Renders the amber "why this was recommended" callout. The text comes from the API — **never invented on the client** |
| `badge` | Festival-urgency label, e.g. `In 3 days`. Sits opposite the stock badge so both can show |
| `showAdd` | `false` for a purely navigational card |

**Rule: do not hand-roll a product tile.** Adding a fourth variant is how the
first three drifted apart.

---

## 9. Home page composition *(rebuilt Day 5)*

The page leads with the festival domain, not the catalogue:

```
Hero  →  badge carries the next festival and its countdown
Next-festival spotlight  →  name, date, countdown, description
                           + its kit box, OR an honest "no ready-made kit yet"
        alongside       →  Required Samagri panel (only `is_required` items)
Recommended For You      →  4 cards, each showing the backend's reason text
The Festival Calendar    →  soonest first; links to the kit if one exists,
                           otherwise to the recommender
Featured Samagri         →  8 cards
Why choose us            →  names the ranking algorithm and whether it was personalised
```

Two rules this composition follows:

1. **Never link to a filter that will come back empty.** A festival with no kit
   links to `/recommendations`, not `/festivals?type=…`.
2. **Say when something does not exist.** 3 of the 6 soonest festivals have no kit.
   The spotlight states that and offers the next best action rather than showing an
   empty slot or an unrelated kit.

---

## 10. Known gaps

| # | Gap | Priority |
|---|---|---|
| 1 | Older admin tables (orders, festivals) are not responsive below ~700px | P1 |
| 2 | No dark mode — the palette is light-only by design | P2 |
| 3 | Focus-visible outlines are browser default, not customised | P2 |
| 4 | No image upload widget; the `image` field is API-only | P1 |
| 5 | Festival kit cards are still bespoke markup, not a shared component | P2 |
| 7 | Toasts are not announced to screen readers (`aria-live` missing) | P1 |
