# Domain-Aware Samagri Search

**Status:** Implemented (Day 12) · **Endpoint:** `GET /api/products/search/?q=`
**Code:** `backend/products/search.py` · **Tests:** `backend/products/tests.py` (41 tests) ·
**Live:** `backend/verify_day12.py` (84 assertions)

---

## 1. Why this exists

`AGENTS.md` §1 requires discovery through **six** entry points, and **Samagri** is one of
them. Until Day 12 that entry point was DRF's `SearchFilter` with
`search_fields = ['name', 'description']` and the default `icontains` lookup. It failed a
shopper in three separate ways, each measured against the seeded catalogue before a line of
this was written — not assumed:

### 1.1 Transliteration

These products are named in romanised Nepali/Sanskrit, and those names have several accepted
spellings. `icontains` knows none of them:

| Typed | Returned | The product is filed as |
|---|---|---|
| `sindur` | **0** | Sindoor Powder (Red) |
| `dhup` | **0** | Loban Dhoop |
| `deep`, `deepak` | **0** | Brass Diyo (Oil Lamp) |
| `karpoor` | **0** | Camphor (Kapur) |
| `sankha` | **0** | Conch Shell (Shankha) |
| `nariyal` | **0** | Dried Coconut (Nariwal) |
| `agarbati` | **0** | Chandan Agarbatti |

Seven zero-result queries, each of them a spelling a shopper would plausibly type.

### 1.2 The domain was not searchable at all

**No product is named after a ritual.** The link lives in `PujaItem` / `KitItem`, which a
substring match over `Product.name` cannot see. So:

| Typed | Returned | Should return |
|---|---|---|
| `pasni` | **0** | The 9 samagri of the Pasni ritual and its kit |
| `griha pravesh` | **0** | The 13 samagri of the Griha Pravesh ritual and its kit |
| `bratabandha` | 1 (a description match) | The 14 samagri of the Bratabandha kit |

`pasni` and `griha pravesh` are seeded rituals with complete kits behind them. Returning
nothing for them is a hole in a headline requirement, not a nicety.

### 1.3 No ranking

Results came back in the model's default order (`-popularity_score`), so `diyo` ranked
*Cotton Wicks* and *Pure Cow Ghee* above **Brass Diyo (Oil Lamp)** — the product the shopper
was obviously after. A search that returns the right products in the wrong order is still a
broken search.

---

## 2. Design

Deterministic, explainable and dependency-free, following `festivals/recommender.py`: a plain
class-free module with no HTTP coupling, additive weights in one module-level `WEIGHTS` table,
and a human sentence for every point awarded. An unexplained result is a black box.

### 2.1 Normalisation

```
normalize(text) = NFKD → ASCII → lower → & becomes "and" → punctuation to spaces
```

NFKD folding is what makes an accented or differently-transliterated spelling land on the
ASCII form the catalogue uses. A minimal plural fold (`wicks` → `wick`) handles the rest —
it is not a stemmer, and pretending otherwise would produce confident nonsense.

### 2.2 Synonyms and transliterations

`SYNONYM_GROUPS` is a tuple of interchangeable terms, curated against the seeded catalogue:

```python
('diyo', 'diya', 'deep', 'deepak', 'deepa', 'dipa', 'deepam', 'lamp', 'oil lamp'),
('sindoor', 'sindur', 'sindor', 'sindhur', 'vermillion', 'vermilion'),
('karpoor', 'kapoor', 'camphor'), ...
```

A stemmer cannot know that *diyo* and *deep* are the same object, and guessing would be
worse than not trying. Querying any member finds the others, and the reason text names the
spelling the catalogue actually uses:

> Matched Sindoor Powder (Red) on the alternative spelling "sindur" → "sindoor"

**Group members are never split into their component words.** Doing that looks harmless and
is not: the group `('thali', 'plate', 'puja plate', 'tray')` would register `puja` as a
synonym of `thali`, so a search for "puja" returned plates and trays; and
`('dhoop', 'dhup', 'dhoop batti')` would register `batti`, so "dhup" returned *Cotton
Wicks*. Both were observed. A multi-word member is matched as a **phrase** instead.

### 2.3 The domain index

`build_domain_index()` loads the active rituals, kits and festivals with the products each one
needs, split into required and optional. A query matches a domain entry when its tokens are
all present in the name (`pasni` against *Pasni (Rice Feeding)*) or when the whole query
appears as a phrase (`griha pravesh`). Token-subset rather than substring, because the
catalogue qualifies its names.

### 2.4 Scoring

```
score = best applicable tier + domain bonus
sort key = (-score, -popularity_score, name)
```

| Code | Points | Awarded when |
|---|---|---|
| `name_exact` | 100 | The normalised name **is** the query |
| `name_prefix` | 80 | The name starts with the query |
| `name_all` | 60 | Every query token appears in the name |
| `name_partial` | 25 + 30×coverage | Some tokens appear in the name |
| `desc_all` | 20 | Every token appears in the description only |
| `desc_partial` | 6 + 12×coverage | Some tokens appear in the description only |
| `name_position` | 12 − 4×index | How early the first matched token sits in the name |
| `domain_required` | 35 | The query names a ritual/kit this product is **required** for |
| `domain_optional` | 18 | Same, but the item is optional in that kit |

**`name_position` is what fixes the ranking.** *Brass Diyo* and *Mustard Oil for Diyo* both
contain "diyo" and both match every token, so without it they score identically and
popularity decides — which is how *Cotton Wicks* came to outrank *Brass Diyo*. Absolute
decay, not relative: normalising by name length made *Tihar Diyo Set* beat *Brass Diyo* purely
because its name was longer, which is an artefact rather than a signal.

**Popularity is a tie-break, never part of the score.** It decides between two products that
matched equally well; it never outranks a better match. That is what keeps the ranking
explainable — *Brass Diyo* is first for "diyo" because it matched best, not because it is
popular.

### 2.5 Candidate narrowing

Scoring happens in Python, but only over a candidate set the database has already narrowed:
products matching any expanded spelling, plus the products of any matched domain. With 35
products scoring everything would also work; the filter keeps the Python pass proportional to
the plausible matches rather than to the catalogue.

---

## 3. Worked examples

**Transliteration** — `GET /api/products/search/?q=sindur`

```
expanded_terms: [sindhur, sindoor, sindor, sindur, vermilion, vermillion]
count: 2
  72  Sindoor Powder (Red)
      · Matched Sindoor Powder (Red) on the alternative spelling "sindur" → "sindoor"
      · "Sindoor Powder (Red)" names it at word 1 of 3
  20  Dashain Tika Set
      · "sindur" appears in the description
```

**Domain** — `GET /api/products/search/?q=pasni`

```
matched_domains: [ritual Pasni (Rice Feeding), kit Pasni (Rice Feeding) Kit]
count: 9
  35  Sindoor Powder (Red)         · Required for Pasni (Rice Feeding) (ritual)
  35  Cotton Wicks (Batti)         · Required for Pasni (Rice Feeding) (ritual)
  ...
  18  Supari (Betel Nut) Pack      · Optional extra for Pasni (Rice Feeding) (kit)
```

Note that the reason distinguishes *required for the ritual* from *optional extra for the
kit* — the same product can be in both, and the shopper is told which.

**Typo** — `GET /api/products/search/?q=sindoer`

```
count: 0
suggestions: [sindor, sindoor, sindur]
```

**Too short** — `GET /api/products/search/?q=a`

```
count: 0
too_short: true
```

---

## 4. Response contract

```json
{
  "query": "sindur",
  "normalized_query": "sindur",
  "tokens": ["sindur"],
  "expanded_terms": ["sindhur", "sindoor", "sindor", "sindur", "vermilion"],
  "matched_domains": [{ "kind": "ritual", "name": "Pasni (Rice Feeding)", "ref": "pasni-rice-feeding" }],
  "suggestions": [],
  "too_short": false,
  "count": 2, "next": null, "previous": null,
  "results": [
    { "id": 5, "name": "Sindoor Powder (Red)", "slug": "...", "price": "50.00", ...,
      "match": { "score": 72, "coverage": 1.0,
                 "codes": ["name_all", "name_position"],
                 "reasons": ["Matched Sindoor Powder (Red) on the alternative spelling ..."] } }
  ]
}
```

- **`?q=` is the documented parameter**; `?search=` is accepted as an alias.
- **`?category=<id>`** narrows the candidate set before ranking, so the storefront's sidebar
  filter keeps working while a query is active. A non-numeric value is ignored rather than
  raising — `category_id='abc'` would otherwise be a 500.
- **`too_short`** exists because "keep typing" and "nothing matched" are different things to
  say, and an empty result set cannot tell them apart.
- **This endpoint is separate from `?search=` on the list endpoints**, deliberately. The
  dashboard's item picker depends on that one and wants a plain substring match over one
  vendor's stock — a different job from ranking a shopper's query. It also keeps the `match`
  block out of every ordinary list response.

---

## 5. Test coverage

41 unit tests in `products/tests.py`, organised by the failure they guard:

| Class | Covers |
|---|---|
| `NormalizationTests` | Diacritics, punctuation, `&`, the plural fold, the 3-character floor |
| `TransliterationTests` | 13 alternative spellings, and the reason naming both spellings |
| `SynonymIsolationTests` | That a group member never becomes a synonym of its own words |
| `RankingTests` | The object outranking a product named after it; determinism |
| `DomainSearchTests` | Ritual → samagri, kit → samagri, required vs optional, inactive rituals |
| `SearchSafetyTests` | Inactive products, short queries, typos, and that every result explains itself |
| `SearchAPITests` | Public access, the `match` block, pagination, the `?search=` alias |

They assert **ordering and explanation**, not response shape. `verify_day12.py` adds 84 live
assertions against the real HTTP API, including the category filter, page non-overlap, and a
regression guard that `?search=` on the list endpoints still behaves as it did.

---

## 6. Frontend

`frontend/src/app/products/page.js` — the catalogue page doubles as the search surface.

- **The URL is shareable.** `/products?q=sindur` loads directly and runs the search. This
  uses `window.history.replaceState`, **not** `router.replace`: measured, replacing a query
  that was already in the URL with a different value did nothing at all on this statically
  prerendered route — no RSC request, and the address bar still read `?q=sindoer` while the
  page showed results for "sindoor". Going from no query to a query worked, which is what
  made it look fine at first.
- **Sorting is hidden while a query is active.** Relevance *is* the sort; offering "Price:
  Low to High" on top of a ranked result set would silently discard the ranking.
- **The page reports what it understood** — the spellings it tried, the rituals it
  recognised — instead of leaving the shopper to guess why a product they never named is on
  screen.
- **Each card carries its strongest reason**, rendered verbatim from the API. The client
  never invents a reason. `ProductCard`'s existing `reason` prop is reused from the
  recommendations work, with a magnifier rather than the sparkle: a search hit is not a
  recommendation and should not be dressed as one.
- **An empty result set is three different messages** — "Keep typing", "did you mean" with
  clickable suggestions, and "nothing matched" — driven by `too_short` and `suggestions`.
- **The catalogue pages.** It previously fetched page 1 and rendered it as though it were
  the whole catalogue: 12 of 35 products, with nothing on screen to say so. Same trap as the
  dashboard's item editor, same fix — a "Show more" that walks `?page=` and says how many are
  left.

---

## 7. Limitations / honest gaps

| Limitation | Detail |
|---|---|
| **The synonym list is curated, not learned** | It covers the seeded catalogue's vocabulary. A new product whose name uses an unlisted spelling will not be found by its alternatives until the group is extended. |
| **English is not translated** | `incense`, `lamp`, `coconut` and friends are listed as synonyms of their Nepali names. There is no general Nepali→English dictionary behind this, and no Devanagari input support. |
| **Scoring is linear, not learned** | No training data exists for relevance here. The weights are hand-tuned and documented; a learned ranker would need click logs this project does not have. |
| **No phrase query syntax** | Quotes, `-exclusion` and `OR` are not supported. A quoted phrase is treated as its words. |
| **`suggest()` is `difflib` over the vocabulary** | Good enough for "did you mean" and dependency-free. It will not correct a misspelling that is far from any known word. |
| **Scoring runs in Python** | Fine for 35 products. At catalogue scale the scoring pass would need to move into the database or a dedicated index. |

---

## 8. Files

| File | Role |
|---|---|
| `backend/products/search.py` | Normalisation, synonyms, the domain index, scoring, suggestions |
| `backend/products/views.py` | `ProductSearchView` |
| `backend/products/urls.py` | `search/` — a public literal, above the slug patterns |
| `backend/products/tests.py` | 41 unit tests |
| `backend/verify_day12.py` | 84 live assertions |
| `frontend/src/app/products/page.js` | The search surface |
| `frontend/src/lib/api.js` | `productsAPI.search()` |
| `frontend/scripts/storefront_check.mjs` | 19 browser assertions |
