# AI Recommendation Engine

**Status:** Implemented (Day 2) · **Endpoint:** `GET /api/festivals/recommendations/`
**Code:** `backend/festivals/recommender.py` · **Tests:** `backend/festivals/tests.py` (23 tests, all passing)

---

## 1. The problem with what was there before

The original `RecommendationsView` looked plausible but was not a recommender:

```python
recommended_products = set()          # <-- a set
for festival in upcoming: ...         # add kit items
for p in popular: recommended_products.add(p.id)
products = Product.objects.filter(id__in=recommended_products)[:12]
```

Three defects, in order of severity:

1. **The ranking was destroyed.** A Python `set` has no order. `filter(id__in=<set>)` with no `order_by` lets the database return rows in whatever order it likes — in practice primary-key order. So the "recommendation" was effectively *"the twelve lowest-numbered products that happen to be in a kit or popular"*. The popularity sort was computed and then thrown away.
2. **There was no explanation.** The API returned bare products plus a hardcoded string. A user could not tell why they were seeing an item, and neither could a reviewer.
3. **The festival signal was dead.** All five `UpcomingFestival` rows had dates in the past, so `upcoming` was empty and no kit items were ever collected. The endpoint silently degraded into "popular products".

A test asserting *"we got 12 products back"* passed against all of this. That is why the tests below assert **ordering** and **explanation**, not just shape.

---

## 2. Design

The model is a **weighted additive signal ranker**. Each candidate product accumulates points from independent signals; the total is therefore always decomposable back into the explanations shown to the user.

```
score(product, user) = Σ signal_i(product, user)
```

Signals are additive rather than multiplicative because explanations must be able to report *"+60 for this reason, +28 for that reason"* in a way a shopkeeper can read.

### Weights

Defined once, in `recommender.py::WEIGHTS`:

| Signal | Code | Points | Fires when |
|---|---|---|---|
| Festival required | `festival_required` | **+60** | Product is a `is_required=True` item of a kit for a festival within 45 days |
| Festival optional | `festival_optional` | **+30** | Same, but `is_required=False` |
| Staple samagri | `staple_samagri` | **+28** | Product's category is in `STAPLE_CATEGORIES` **and** a festival is within 21 days |
| Category affinity | `user_category` | **+22** | User has previously ordered from this category |
| Kit affinity | `user_kit_affinity` | **+16** | Product shares a kit with something the user bought |
| Repeat purchase | `user_repeat` | **+14** | User has ordered this exact product |
| Popularity | `popular` | **+8 … +12** | Always (scaled by `popularity_score // 4`) |

### Why festival signal outweighs popularity

`festival_required` (60) is five times `popularity_max` (12). This is deliberate and it is the core domain decision: for a Puja Samagri store, *"you will need this in five days because it is required for Dashain"* is a categorically stronger statement than *"this sells well"*. A generic best-seller list is exactly the failure mode the brief warned against.

### The staple-samagri signal — why it exists

Some festivals have no curated kit. Ganesh Chaturthi is a clear example: there is no `FestivalKit` with `festival_type='other'`, so the kit-based signal is **structurally blind** to it — even when it is six days away.

Rather than fudge the weights to paper over this, the engine models the real domain fact: certain items are *nithya samagri* — used in essentially every Hindu ritual in the valley regardless of occasion. Diyo, batti, dhoop, sindoor, kalava, coconut. When a festival is close, a household genuinely needs these.

```python
STAPLE_CATEGORIES = {
    'Dhoop & Agarbatti', 'Tika & Sindoor', 'Puja Flowers & Garlands',
    'Sacred Threads', 'Puja Oils & Ghee', 'Offerings & Prasad',
}
STAPLE_WINDOW_DAYS = 21
```

The signal is explicitly **capped below** `festival_required` (28 < 60), so a generic staple can never outrank an explicitly required samagri. There is a test for exactly this (`test_staple_ranks_below_required_kit_item`).

> **Known data-quality issue, documented not hidden:** `Cotton Wicks (Batti)` is categorised under *"Puja Flowers & Garlands"* in the seed data. Wicks are not flowers. It works incidentally (the category is a staple category anyway), but the categorisation is wrong and should be corrected in the admin UI.

### Tie-breaking

Score alone produces ties. The sort key is:

```python
(-score, urgency_rank, -popularity_score, product.id)
```

The final `product.id` makes ordering **fully deterministic** — the property the old `set()` implementation could not provide. `test_ranking_is_deterministic` asserts this across five repeated builds.

### Urgency

| Bucket | Condition |
|---|---|
| `urgent` | ≤ 7 days to the associated festival |
| `soon` | ≤ 21 days |
| `upcoming` | ≤ 45 days |
| `None` | No festival association |

---

## 3. Worked example

Live response for the seeded `testuser`, limit 5. `testuser` has real order history.

```
Premium Dhoop Batti (Pack of 20)              score = 198
   +60  [festival_required]  Required for Ghatasthapana (Dashain Begins) (33 days away)
   +60  [festival_required]  Required for Vijaya Dashami (43 days away)
   +28  [staple_samagri]     Everyday puja essential — needed for Ganesh Chaturthi in 6 days
   +16  [user_kit_affinity]  Goes with items you have bought before
   +22  [user_category]      You often buy from Dhoop & Agarbatti
   +12  [popular]            Popular item (score 89)
                             ─────
                             198   ✓ 60+60+28+16+22+12 = 198
```

Every number is traceable. `test_score_equals_sum_of_reason_points` asserts this invariant for all products in every test fixture.

Anonymous visitors get the same product set minus the three `user_*` signals, and the response carries `meta.personalised: false` so the UI can honestly say *"Sign in to personalise these results"*.

---

## 4. Response contract

```jsonc
{
  "upcoming_festivals": [ { "id": 8, "name": "Indra Jatra", "date": "2026-10-15", ... } ],
  "recommended_products": [
    {
      "id": 1, "name": "Premium Dhoop Batti (Pack of 20)", "slug": "...",
      "price": "120.00", "stock": 196, "category_name": "Dhoop & Agarbatti",
      "recommendation": {
        "score": 198,
        "urgency": "upcoming",
        "festival_name": "Ghatasthapana (Dashain Begins)",
        "festival_type": "dashain",
        "days_until": 33,
        "reasons": [
          { "code": "festival_required", "points": 60, "text": "Required for ..." }
        ]
      }
    }
  ],
  "meta": {
    "algorithm": "weighted-signal-ranker", "version": 1,
    "window_days": 45, "personalised": true, "candidate_count": 21
  }
}
```

`?limit=` is clamped to `1..48`; a non-numeric value silently falls back to 12 rather than erroring.

---

## 5. Test coverage

`backend/festivals/tests.py` — **23 tests, all passing** (`python manage.py test festivals`).

The suite is written to fail against the old implementation:

| Test | Property asserted |
|---|---|
| `test_required_item_outranks_optional_item` | Required samagri beats optional extra |
| `test_festival_items_outrank_unrelated_popular_item` | Domain signal beats raw popularity |
| `test_ranking_is_deterministic` | Identical order across 5 rebuilds |
| `test_sooner_festival_is_preferred` | Nearer festival → higher urgency |
| `test_every_recommendation_has_a_reason` | No black-box recommendations |
| `test_score_equals_sum_of_reason_points` | Score fully decomposable |
| `test_reason_mentions_festival_and_days` | Explanation is human-readable |
| `test_excludes_out_of_stock_and_inactive` | Sold-out/inactive never recommended |
| `test_festival_outside_window_contributes_nothing` | 45-day window respected |
| `test_inactive_festival_is_ignored` | `is_active=False` honoured |
| `test_staple_signal_fires_for_kitless_festival` | Signal works where kits are absent |
| `test_staple_signal_silent_when_no_festival_is_close` | No spurious staple boost |
| `test_curated_kit_festival_badge_wins_over_staple` | More specific association wins |
| `test_staple_ranks_below_required_kit_item` | Cap enforced |
| `test_personalisation_boosts_previously_ordered_product` | History affects ranking |
| `test_anonymous_user_is_not_personalised` | `meta.personalised` correct |
| `test_limit_is_respected` | Limit honoured |
| (+ 6 endpoint-contract tests) | HTTP shape, public access, clamping |

---

## 6. Frontend

`frontend/src/app/recommendations/page.js` renders the top reason for each product in an amber callout box, plus an urgency badge (`In 6 days`) when `urgency === 'urgent'`.

**Important:** the client never invents a reason. It renders `reason.text` from the API, with `REASON_LABELS` used only as a fallback for an unrecognised `code`. If the backend stops explaining, the UI shows nothing rather than fabricating a rationale.

Verified against live data: **8/8 rendered recommendations carried an explanation**; personalised response carried `user_repeat`, `user_kit_affinity` and `user_category` reasons.

---

## 7. Limitations / honest gaps

- **No collaborative filtering.** There is one customer with 8 orders. User-user similarity is not computable at this volume, and claiming otherwise would be dishonest. The `user_*` signals are popularity-plus-history heuristics, which is the correct choice at this data size.
- **Weights are hand-tuned, not learned.** They encode domain judgement. This is defensible and explainable; a learned ranker would need orders of magnitude more data.
- **`Reasons` are not ranked for display.** The UI shows `reasons[0]`, which is insertion-ordered (festival first). The full list is returned for a future "why?" expander.
- **No A/B measurement.** Click-through on recommendations is not tracked, so the weights are unvalidated against real behaviour.
- **Cold start for new products** relies entirely on the popularity fallback.

---

## 8. Files

| File | Role |
|---|---|
| `backend/festivals/recommender.py` | `Recommender`, `ScoredProduct`, `WEIGHTS`, `serialize_recommendations` |
| `backend/festivals/views.py` | `RecommendationsView` — HTTP + serialization only |
| `backend/festivals/tests.py` | 23 tests |
| `backend/festivals/management/commands/refresh_festivals.py` | Repairs the dead festival calendar |
| `frontend/src/app/recommendations/page.js` | Renders explanations and urgency |
| `frontend/src/app/recommendations/recommendations.module.css` | Card, reason box, urgency badge |
