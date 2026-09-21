"""Day 12 — domain-aware samagri search, over the real HTTP API.

`AGENTS.md` §1 requires discovery through six entry points and **Samagri** is one of
them. Before this work that entry point was DRF's `SearchFilter` with
`search_fields = ['name', 'description']`, which failed a shopper in three ways. Each
one is asserted below, and each was measured against the seeded catalogue first:

* **Transliteration.** `sindur` returned 0 products — the product is "Sindoor
  Powder". Same for `dhup`, `deep`, `karpoor`, `sankha`, `nariyal`, `agarbati`.
* **The domain was not searchable.** No product is named after a ritual, so `pasni`
  and `griha pravesh` returned **0** products although both are seeded rituals with a
  complete kit behind them.
* **No ranking.** Results came back in `-popularity_score` order, so `diyo` ranked
  "Cotton Wicks" and "Pure Cow Ghee" above "Brass Diyo (Oil Lamp)".

Two things this script is careful about, because both have burned this project:

* **It asserts ordering and explanation, not just shape.** A search that returns the
  right products in the wrong order is still a broken search. Every result must also
  say why it is there, with a code traceable to the weights table.
* **It reads before it asserts.** Where a check depends on a product existing, it
  looks the product up first and reports a labelled SKIP rather than a false failure.

Read-only: it writes nothing, so there is nothing to purge afterwards.

Usage:  ./venv/Scripts/python.exe verify_day12.py
"""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://127.0.0.1:8000')
PASS = 0
FAIL = 0
SKIP = 0
FAILURES = []

# Every code the scorer is allowed to emit. Kept in step with
# `products/search.py::REASON_CODES`; a code outside this set means the API invented a
# reason with no weight behind it, which is a score nobody can trace.
KNOWN_CODES = {
    'name_exact', 'name_prefix', 'name_all', 'name_partial',
    'desc_all', 'desc_partial', 'name_position',
    'domain_required', 'domain_optional',
}


def check(label, condition, detail=''):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f'  PASS  {label}')
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f'  FAIL  {label}  {detail}')


def skip(label, reason):
    global SKIP
    SKIP += 1
    print(f'  SKIP  {label}  ({reason})')


def section(title):
    print(f'\n=== {title} ===')


def request(method, path, token=None, body=None, timeout=30):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, raw
    except Exception as exc:  # noqa: BLE001 - reported as a check failure
        return 0, str(exc)


def search(query, **extra):
    params = {'q': query}
    params.update(extra)
    return request('GET', '/api/products/search/?' + urllib.parse.urlencode(params))


def names(payload):
    return [row['name'] for row in payload.get('results', [])]


def first_name(payload):
    rows = payload.get('results', [])
    return rows[0]['name'] if rows else None


# ---------------------------------------------------------------- access

def test_public_and_shaped():
    section('Search is public, and says what it understood')

    status, body = search('sindur')
    check('an anonymous reader can search', status == 200, f'status={status}')
    if status != 200:
        return None

    check('the response carries the query it understood',
          body.get('normalized_query') == 'sindur', f"got={body.get('normalized_query')!r}")
    check('it reports every spelling it tried',
          {'sindur', 'sindoor', 'sindor'} <= set(body.get('expanded_terms', [])),
          f"terms={body.get('expanded_terms')}")
    check('it reports the domains the query named',
          'matched_domains' in body, f'keys={sorted(body)}')
    check('it is paginated like every other list',
          {'count', 'next', 'previous', 'results'} <= set(body),
          f'keys={sorted(body)}')
    check('a short query is flagged rather than silently searched',
          search('a')[1].get('too_short') is True, 'too_short not reported')
    check('and an empty query is flagged too',
          search('')[1].get('too_short') is True, 'too_short not reported')
    check('a real query is not flagged as short',
          body.get('too_short') is False, f"too_short={body.get('too_short')}")
    return body


# ---------------------------------------------------------------- transliteration

TRANSLITERATIONS = (
    ('sindur', 'Sindoor Powder (Red)'),
    ('sindor', 'Sindoor Powder (Red)'),
    ('vermillion', 'Sindoor Powder (Red)'),
    ('dhup', 'Loban Dhoop'),
    ('deep', 'Brass Diyo (Oil Lamp)'),
    ('diya', 'Brass Diyo (Oil Lamp)'),
    ('karpoor', 'Camphor (Kapur) - 50g'),
    ('sankha', 'Conch Shell (Shankha)'),
    ('nariyal', 'Dried Coconut (Nariwal)'),
    ('agarbati', 'Chandan Agarbatti'),
    ('incense', 'Chandan Agarbatti'),
    ('thali', 'Copper Puja Plate (Thali)'),
    ('ghanta', 'Puja Bell (Ghanti)'),
    ('supari', 'Supari (Betel Nut) Pack'),
    ('coconut', 'Dried Coconut (Nariwal)'),
)


def test_transliteration(catalogue):
    section('A second spelling of a Nepali term finds the product')

    for query, expected in TRANSLITERATIONS:
        if expected not in catalogue:
            skip(f'“{query}” finds “{expected}”', 'not in the seeded catalogue')
            continue
        status, body = search(query)
        check(f'“{query}” finds “{expected}”',
              status == 200 and expected in names(body),
              f'got={names(body)[:4]}')


def test_reason_names_the_spelling():
    section('The explanation names the spelling the catalogue uses')

    status, body = search('sindur')
    rows = body.get('results', []) if status == 200 else []
    if not rows:
        skip('the reason names both spellings', 'no results')
        return
    reasons = ' '.join(rows[0].get('match', {}).get('reasons', []))
    check('the reason names the spelling the shopper typed', 'sindur' in reasons, reasons[:160])
    check('and the spelling the catalogue files it under', 'sindoor' in reasons.lower(), reasons[:160])


# ---------------------------------------------------------------- the domain

def test_domain_search():
    section('A ritual name finds the samagri it needs')

    for query, ritual in (('pasni', 'Pasni (Rice Feeding)'),
                          ('griha pravesh', 'Griha Pravesh'),
                          ('bratabandha', 'Bratabandha')):
        status, body = search(query)
        check(f'“{query}” returns samagri', status == 200 and body['count'] > 0,
              f'count={body.get("count") if status == 200 else status}')

        matched = [entry['name'] for entry in body.get('matched_domains', [])]
        check(f'“{query}” names the ritual it matched', ritual in matched, f'matched={matched}')

        # The whole point: no product is named after a ritual. If one were, this
        # would only be proving a substring match and the domain link would be
        # untested.
        check(f'no result for “{query}” is named after it',
              not any(query.split()[0] in name.lower() for name in names(body)),
              f'names={names(body)[:5]}')

    status, body = search('pasni')
    codes = {code for row in body.get('results', []) for code in row.get('match', {}).get('codes', [])}
    check('a domain hit is recorded as a required item', 'domain_required' in codes,
          f'codes={sorted(codes)}')


def test_domain_covers_kit_and_ritual():
    section('The ritual and its kit are both reported')

    status, body = search('pasni')
    kinds = {entry['kind'] for entry in body.get('matched_domains', [])}
    check('the ritual is reported', 'ritual' in kinds, f'kinds={sorted(kinds)}')
    check('the kit assembled for it is reported too', 'kit' in kinds, f'kinds={sorted(kinds)}')
    for entry in body.get('matched_domains', []):
        check(f'the {entry["kind"]} carries something to link back with',
              bool(entry.get('ref')), f'entry={entry}')


# ---------------------------------------------------------------- ranking

def test_ranking():
    section('The product itself outranks one that merely mentions it')

    status, body = search('diyo')
    rows = names(body) if status == 200 else []
    check('“diyo” returns the lamps', 'Brass Diyo (Oil Lamp)' in rows, f'got={rows[:5]}')
    if 'Brass Diyo (Oil Lamp)' in rows and 'Mustard Oil for Diyo (500ml)' in rows:
        check('the lamp ranks above the oil named after it',
              rows.index('Brass Diyo (Oil Lamp)') < rows.index('Mustard Oil for Diyo (500ml)'),
              f'order={rows}')
    else:
        skip('the lamp ranks above the oil', 'one of the two products is missing')

    status, body = search('sindoor')
    check('an exact name match ranks first',
          first_name(body) == 'Sindoor Powder (Red)', f'first={first_name(body)}')

    # Determinism: two identical calls must not reshuffle. Two *diyo* calls — the
    # first version of this compared the sindoor payload against a diyo one and
    # reported a false failure, which is its own small lesson about naming a variable
    # `body` in a long function.
    _, diyo_again = search('diyo')
    check('the order is stable across requests', rows == names(diyo_again),
          f'{rows[:3]} vs {names(diyo_again)[:3]}')


def test_position_reason():
    section('A position-based reason is recorded where it applies')

    status, body = search('diyo')
    for row in body.get('results', []):
        if row['name'] == 'Brass Diyo (Oil Lamp)':
            check('the match explains where in the name it landed',
                  'name_position' in row['match']['codes'], f"codes={row['match']['codes']}")
            return
    skip('the position reason is recorded', 'the product was not in the results')


# ---------------------------------------------------------------- explanation

def test_every_result_explains_itself():
    section('Every result explains itself, and the codes are all real')

    for query in ('sindoor', 'diyo', 'pasni', 'puja', 'thali', 'bratabandha'):
        status, body = search(query)
        if status != 200:
            check(f'“{query}” returns 200', False, f'status={status}')
            continue
        rows = body.get('results', [])
        check(f'every result for “{query}” carries a reason',
              rows and all(row['match']['reasons'] for row in rows),
              f'rows={len(rows)}')
        unknown = {code for row in rows for code in row['match']['codes']} - KNOWN_CODES
        check(f'every reason code for “{query}” is one the ranker declares',
              not unknown, f'unknown={sorted(unknown)}')
        check(f'every score for “{query}” is positive',
              all(row['match']['score'] > 0 for row in rows),
              f'scores={[row["match"]["score"] for row in rows][:5]}')


# ---------------------------------------------------------------- suggestions

def test_suggestions():
    section('A typo is offered a correction from the catalogue’s own vocabulary')

    status, body = search('sindoer')
    check('a misspelling matches nothing', status == 200 and body['count'] == 0,
          f'count={body.get("count") if status == 200 else status}')
    check('and is offered a correction', 'sindoor' in body.get('suggestions', []),
          f"suggestions={body.get('suggestions')}")

    status, body = search('camphour')
    check('another misspelling is corrected too', 'camphor' in body.get('suggestions', []),
          f"suggestions={body.get('suggestions')}")

    status, body = search('sindoor')
    check('no suggestion is offered when something matched',
          body.get('suggestions') == [], f"suggestions={body.get('suggestions')}")

    status, body = search('xyzzy')
    check('nonsense returns an empty 200, not a 404',
          status == 200 and body['count'] == 0, f'status={status}')
    check('and is not mislabelled as too short', body.get('too_short') is False, '')


# ---------------------------------------------------------------- filters & paging

def test_category_filter_still_works():
    section('The category filter narrows a search instead of being ignored')

    status, categories = request('GET', '/api/products/categories/')
    if status != 200 or not categories:
        skip('the category filter narrows a search', 'no categories returned')
        return

    # Pick the category that "Sindoor Powder (Red)" belongs to, so the filtered and
    # unfiltered result sets are guaranteed to differ.
    status, body = search('sindoor')
    if not body.get('results'):
        skip('the category filter narrows a search', 'no results to filter')
        return
    target = body['results'][0]
    category_id = target['category']

    status, filtered = search('sindoor', category=category_id)
    check('a filtered search returns 200', status == 200, f'status={status}')
    check('it returns the product that is in that category',
          target['name'] in names(filtered), f'got={names(filtered)}')
    check('every row belongs to the requested category',
          all(row['category'] == category_id for row in filtered['results']),
          f"categories={[row['category'] for row in filtered['results']]}")

    status, other = search('sindoor', category=999999)
    check('an unknown category is an empty result, not an error',
          status == 200 and other['count'] == 0, f'status={status}')

    status, bad = search('sindoor', category='not-a-number')
    check('a non-numeric category does not 500', status == 200, f'status={status}')


def test_pagination():
    section('Search results page, and the pages do not overlap')

    status, first = search('puja', page=1)
    status2, second = search('puja', page=2)
    check('page 1 returns 200', status == 200, f'status={status}')
    check('page 2 returns 200', status2 == 200, f'status={status2}')
    if status != 200 or status2 != 200:
        return

    ids_first = {row['id'] for row in first['results']}
    ids_second = {row['id'] for row in second['results']}
    check('page 1 has rows', bool(ids_first), 'empty page 1')
    check('the total is larger than one page', first['count'] > len(first['results']),
          f"count={first['count']} page={len(first['results'])}")
    check('page 2 exists', bool(ids_second), 'empty page 2')
    check('no row appears on both pages', not (ids_first & ids_second),
          f'overlap={sorted(ids_first & ids_second)}')
    check('page 1 links forward', bool(first['next']), 'no next link')


def test_inactive_products_never_appear():
    section('A withdrawn product cannot be found')

    # An unknown name is an empty result, not a fallback to something else. The term
    # has to be one the catalogue genuinely cannot match: the first version of this
    # used "Retired Nonexistent Samagri", and "samagri" is a real word in several
    # product names and descriptions, so it correctly matched one. Read the data
    # before choosing a probe for it.
    status, body = search('Zzzz Nonexistent Product')
    check('a query matching nothing returns an empty 200',
          status == 200 and body['count'] == 0,
          f'status={status} count={body.get("count") if status == 200 else "?"}')

    # The inactive case itself cannot be established from here: this script is
    # read-only and nothing in the seeded catalogue is withdrawn. It is covered where
    # it can be — `products/tests.py::SearchSafetyTests
    # .test_an_inactive_product_is_never_returned` builds one. Reported as a SKIP so
    # the gap is visible rather than implied to be covered.
    skip('a withdrawn product is excluded from search',
         'read-only script; covered by SearchSafetyTests in products/tests.py')


def test_list_search_parameter_unchanged():
    section('The list endpoint’s ?search= is untouched')

    # The dashboard's item picker depends on `?search=` on the admin product list, and
    # it wants a plain substring match over one vendor's stock — a different job from
    # ranking a shopper's query. The new endpoint must not have replaced it.
    status, body = request('GET', '/api/products/?search=dhoop&page=1')
    check('?search= on the public list still returns 200', status == 200, f'status={status}')
    if status == 200:
        check('and still finds a substring match',
              any('dhoop' in name.lower() for name in names(body)),
              f'got={names(body)}')
        check('and carries no search-specific payload',
              'matched_domains' not in body, 'the list grew a search-only field')


def main():
    print(f'Verifying against {BASE}')

    status, catalogue = request('GET', '/api/products/?page=1&page_size=100')
    if status == 200 and isinstance(catalogue, dict):
        known = set(names(catalogue))
    else:
        known = set()
    # The catalogue pages at 12, so walk the rest before asserting a product exists.
    page = 2
    while isinstance(catalogue, dict) and catalogue.get('next') and page <= 10:
        status, more = request('GET', f'/api/products/?page={page}&page_size=100')
        if status != 200 or not isinstance(more, dict):
            break
        known |= set(names(more))
        page += 1
    print(f'  catalogue carries {len(known)} products')

    test_public_and_shaped()
    test_transliteration(known)
    test_reason_names_the_spelling()
    test_domain_search()
    test_domain_covers_kit_and_ritual()
    test_ranking()
    test_position_reason()
    test_every_result_explains_itself()
    test_suggestions()
    test_category_filter_still_works()
    test_pagination()
    test_inactive_products_never_appear()
    test_list_search_parameter_unchanged()

    print(f'\n{"=" * 60}')
    print(f'  {PASS} passed, {FAIL} failed, {SKIP} skipped')
    if FAILURES:
        print('  Failed checks:')
        for name in FAILURES:
            print(f'    - {name}')
    print(f'{"=" * 60}')
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
