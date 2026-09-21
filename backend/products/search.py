"""Domain-aware samagri search.

Why this exists
---------------
``AGENTS.md`` §1 requires discovery through six entry points, and **Samagri** is one
of them. Until now that entry point was DRF's ``SearchFilter`` with
``search_fields = ['name', 'description']`` and the default ``icontains`` lookup,
which fails a shopper in three separate ways. All three were measured against the
seeded catalogue before this module was written, not assumed:

1. **Transliteration.** These products are named in romanised Nepali/Sanskrit, and
   those names have several accepted spellings. ``sindur`` returned **0** results
   (the product is "Sindoor Powder"), ``dhup`` 0 ("Dhoop"), ``deep`` 0 ("Diyo"),
   ``karpoor`` 0 ("Kapur"), ``sankha`` 0 ("Shankha"), ``nariyal`` 0 ("Nariwal"),
   ``agarbati`` 0 ("Agarbatti").
2. **The domain relationships were not searchable at all.** No *product* is named
   after a ritual — the link lives in ``PujaItem`` / ``KitItem``. So searching a
   ritual by name found nothing: ``pasni`` and ``griha pravesh`` returned **0**
   results, although both are seeded rituals with a complete kit behind them. That
   is a hole in a headline requirement, not a nicety.
3. **No ranking.** Results came back in the model's default order
   (``-popularity_score``), so ``diyo`` ranked "Cotton Wicks" and "Pure Cow Ghee"
   above "Brass Diyo (Oil Lamp)" — the product the shopper was obviously after.

Design
------
Deterministic, explainable and dependency-free, following
``festivals/recommender.py``: a plain class with no HTTP coupling, additive weights
in one module-level :data:`WEIGHTS` table, and a human sentence for every point
awarded, so the storefront can say *why* an item is in the results. An unexplained
result is a black box, and this project already has one explainable ranker — search
should not be the place where that standard slips.

The score is a raw integer, deliberately not normalised to 0..1. Reasons are far
more useful to a shopper than a percentage, and a raw number is easier to debug.

Changing :data:`WEIGHTS` or :data:`SYNONYM_GROUPS` means updating
``docs/SEARCH.md`` — the numbers there are reproduced from this file.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from django.db.models import Q

from .models import Product

# ---------------------------------------------------------------------------
# Weights — every point awarded is traceable to one of these constants.
# ---------------------------------------------------------------------------

WEIGHTS = {
    # The normalised name is exactly the query.
    'name_exact': 100,
    # The name begins with the query phrase — the strongest signal short of exact.
    'name_prefix': 80,
    # Every query token appears somewhere in the name.
    'name_all': 60,
    # Some but not all tokens appear in the name; scaled by how many did.
    'name_partial_base': 25,
    'name_partial_span': 30,
    # Every token appears in the description only.
    'desc_all': 20,
    # Some tokens appear in the description only; scaled.
    'desc_partial_base': 6,
    'desc_partial_span': 12,
    # How early in the name the first matched token sits, scaled to 0..this. A
    # product whose *own* noun matches ("Brass **Diyo**") is the thing the shopper
    # asked for; one that merely mentions it ("Mustard Oil for **Diyo**") is
    # related stock. Without this, both score identically as "every token is in the
    # name" and popularity decides — which is how "Cotton Wicks" outranked
    # "Brass Diyo" before this module existed.
    'name_position': 12,
    # The query names a ritual, festival or kit, and this product is one of its
    # REQUIRED items. This is the domain signal a generic shop cannot have, and it
    # is what makes "pasni" and "griha pravesh" return anything at all.
    'domain_required': 35,
    # Same, but the item is optional in that kit / ritual.
    'domain_optional': 18,
}

# Tie-break only: popularity never outranks a better textual or domain match, it
# only decides between two products that matched equally well. Keeping it out of
# the score is what makes the ranking explainable — "Brass Diyo" is first for
# "diyo" because it matched best, not because it is popular.
POPULARITY_TIEBREAK = True

# Every reason code a result can carry, declared explicitly rather than left implicit
# in the scorer. A reason code with no weight behind it is a score nobody can trace,
# and a typo in one would otherwise be invisible — the tests check membership here.
#
# The two ``*_partial`` tiers are the exception to the 1:1 mapping: they are a base
# plus a span scaled by how many tokens matched, so they have no single WEIGHTS entry.
PARTIAL_CODES = frozenset({'name_partial', 'desc_partial'})
REASON_CODES = frozenset({
    'name_exact', 'name_prefix', 'name_all', 'name_partial',
    'desc_all', 'desc_partial', 'name_position',
    'domain_required', 'domain_optional',
})

# ---------------------------------------------------------------------------
# Synonyms and transliterations
# ---------------------------------------------------------------------------
# Each tuple is one group of interchangeable terms. Querying any member finds the
# others, and the reason text names the variant the catalogue actually uses, so a
# shopper who typed "sindur" is told the product is filed under "Sindoor".
#
# These are curated against the seeded catalogue rather than generated. A stemmer
# cannot know that "diyo" and "deep" are the same object, and guessing would
# produce confident nonsense — the one thing a search box must not do.
SYNONYM_GROUPS = (
    # Lamps and lights
    ('diyo', 'diya', 'deep', 'deepak', 'deepa', 'dipa', 'deepam', 'lamp', 'oil lamp'),
    ('batti', 'bati', 'wick', 'wicks', 'baati'),
    ('ghanti', 'ghanta', 'bell'),
    # Incense — agarbatti and dhoop are separate products here, so they stay
    # separate groups; shoppers do conflate them, but merging would put a dhoop
    # product under "incense" and quietly mis-file the catalogue.
    ('agarbatti', 'agarbati', 'agarabatti', 'agarabati', 'incense', 'incense stick'),
    ('dhoop', 'dhup', 'dhoopbatti', 'dhupbatti', 'dhoop batti'),
    ('loban', 'lobhan', 'guggul', 'guggal'),
    # Powders and pastes
    ('sindoor', 'sindur', 'sindor', 'sindhur', 'vermillion', 'vermilion'),
    ('kumkum', 'kumkuma', 'kunku', 'kunkum'),
    ('chandan', 'chandanam', 'sandal', 'sandalwood'),
    ('abir', 'abeer', 'gulal'),
    ('tika', 'tilak', 'tika paste'),
    ('kapur', 'karpoor', 'kapoor', 'camphor'),
    # Vessels and implements
    ('kalash', 'kalas', 'kalasha', 'lota'),
    ('thali', 'plate', 'puja plate', 'tray'),
    ('shankha', 'sankha', 'shankh', 'sankh', 'conch', 'conch shell'),
    ('hawan', 'havan', 'homa', 'hom', 'yagya', 'hawan kund'),
    # Offerings
    ('nariwal', 'nariyal', 'narial', 'coconut', 'narikel'),
    ('supari', 'betel nut', 'betelnut', 'betel'),
    ('naivedya', 'naivedyam', 'prasad', 'bhog'),
    ('batasha', 'batasa', 'sugar drops'),
    ('ghee', 'ghrit', 'ghrita'),
    ('til', 'sesame', 'gingelly'),
    ('rudraksha', 'rudraksh', 'rudrakshya'),
    # Threads
    ('janai', 'janeu', 'upavita', 'sacred thread'),
    ('kalava', 'mauli', 'kalawa', 'mouli', 'red thread'),
    # Festivals and occasions. These also reach the domain index, but listing them
    # here means a shopper who types the English or the alternative name still
    # lands on the festival's samagri.
    ('dashain', 'dasain', 'dussehra', 'vijaya dashami', 'bijaya dashami'),
    ('tihar', 'deepawali', 'diwali', 'laxmi puja'),
    ('shivaratri', 'shivratri', 'maha shivaratri', 'mahashivaratri'),
    ('bratabandha', 'bratabandh', 'batabandha', 'upanayan', 'upanayana', 'upnayan'),
    ('pasni', 'pasne', 'rice feeding', 'annaprasan', 'annaprashan'),
    ('griha pravesh', 'grihapravesh', 'griha praves', 'housewarming', 'griha'),
    ('shraddha', 'sraddha', 'shradha'),
)

# Terms too short or too common to be worth expanding — expanding "the" or "set"
# would flood the results with everything.
STOPWORDS = frozenset({
    'a', 'an', 'and', 'for', 'of', 'the', 'with', 'to', 'in', 'on', 'set', 'pack',
    'piece', 'pieces', 'pcs', 'bundle', 'roll', 'small', 'large', 'big', 'new',
})

MIN_QUERY_LENGTH = 2

_PUNCTUATION = re.compile(r'[^a-z0-9\s]+')
_WHITESPACE = re.compile(r'\s+')


def normalize(text):
    """Lower-case, strip diacritics and punctuation, collapse whitespace.

    ``unicodedata.normalize('NFKD', ...)`` is what makes an accented or Devanagari-
    transliterated spelling fold onto the ASCII form the catalogue uses, so
    "Til Oil" and "til  oil" and "TĪl Oil" all normalise the same way.
    """
    if not text:
        return ''
    decomposed = unicodedata.normalize('NFKD', str(text))
    ascii_only = decomposed.encode('ascii', 'ignore').decode('ascii')
    lowered = ascii_only.lower().replace('&', ' and ')
    return _WHITESPACE.sub(' ', _PUNCTUATION.sub(' ', lowered)).strip()


def _stem(token):
    """A minimal plural fold. Not a stemmer — just enough for "wicks" == "wick"."""
    if len(token) > 3 and token.endswith('s'):
        return token[:-1]
    return token


def tokenize(text):
    return [t for t in normalize(text).split() if t]


def _build_synonym_index():
    """term -> every other spelling in its group. Keys are whole terms.

    **Group members are never split into their component words.** Doing that looks
    harmless and is not: the group ``('thali', 'plate', 'puja plate', 'tray')``
    would register ``puja`` as a synonym of ``thali``, so a search for "puja"
    returned plates and trays, and the group ``('dhoop', 'dhup', 'dhoop batti')``
    would register ``batti`` — so "dhup" returned *Cotton Wicks*. Both were
    observed, not hypothesised. A multi-word member is matched as a phrase instead
    (see :func:`_hits_in`).
    """
    index = {}
    for group in SYNONYM_GROUPS:
        members = frozenset(normalize(term) for term in group)
        for term in members:
            index.setdefault(term, set()).update(members)
    return {term: frozenset(values) for term, values in index.items()}


SYNONYMS = _build_synonym_index()


def expand_token(token):
    """Every spelling of ``token`` that should be treated as the same word."""
    variants = {token}
    variants.update(SYNONYMS.get(token, ()))
    return {v for v in variants if v and v not in STOPWORDS}


def expand_query(query):
    """The full set of spellings the query should be matched against."""
    tokens = tokenize(query)
    expanded = set()
    for token in tokens:
        if token in STOPWORDS:
            continue
        expanded.update(expand_token(token))
    return tokens, expanded


# ---------------------------------------------------------------------------
# The domain index — rituals, kits and festivals, by name
# ---------------------------------------------------------------------------

@dataclass
class DomainMatch:
    """One ritual / kit / festival the query names.

    ``ref`` is what the storefront needs to link back to the entity, and it is not
    the same kind of value for all three: a ritual is addressable by its slug
    (``/pujas/<slug>``), while ``FestivalKit`` has no slug column at all and a
    festival is reached by its type (``/festivals?type=<festival_type>``). Hence
    ``ref`` rather than ``slug`` — the name says only "this identifies it".
    """

    kind: str            # 'ritual' | 'kit' | 'festival'
    name: str
    ref: str
    required_product_ids: set = field(default_factory=set)
    optional_product_ids: set = field(default_factory=set)

    @property
    def label(self):
        return {'ritual': 'ritual', 'kit': 'kit', 'festival': 'festival'}[self.kind]


def build_domain_index():
    """Load the rituals, kits and festivals with the products each one needs.

    Imported inside the function on purpose: ``festivals`` already imports
    ``products.models``, and keeping this import local means ``products.search``
    can be imported from anywhere — including a management command or a test —
    without depending on app-loading order.
    """
    from festivals.models import FestivalKit, KitItem, Puja, PujaItem, UpcomingFestival

    entries = []

    for puja in Puja.objects.filter(is_active=True).prefetch_related('items'):
        entry = DomainMatch('ritual', puja.name, puja.slug)
        for item in puja.items.all():
            target = entry.required_product_ids if item.is_required else entry.optional_product_ids
            target.add(item.product_id)
        entries.append(entry)

    for kit in FestivalKit.objects.filter(is_active=True).prefetch_related('items'):
        entry = DomainMatch('kit', kit.name, kit.festival_type)
        for item in kit.items.all():
            target = entry.required_product_ids if item.is_required else entry.optional_product_ids
            target.add(item.product_id)
        entries.append(entry)

    # A festival with no kit still deserves to be findable — the home page says so
    # plainly, and 3 of the seeded rituals have no kit at all. It contributes no
    # products of its own, but it can still name-match and be reported back.
    for festival in UpcomingFestival.objects.filter(is_active=True):
        entries.append(DomainMatch('festival', festival.name, festival.festival_type))

    return entries


def match_domains(tokens, normalized_query, entries):
    """Which rituals / kits / festivals does this query name?

    A name matches when the query's tokens are all present in it ("pasni" against
    "Pasni (Rice Feeding)"), or when the whole query appears as a phrase ("griha
    pravesh"). Token-subset rather than phrase containment, because the catalogue
    qualifies its names — the product is "Pasni (Rice Feeding)", not "Pasni".
    """
    matched = []
    for entry in entries:
        name_tokens = set(tokenize(entry.name))
        stems = {_stem(t) for t in name_tokens}
        if normalized_query and normalized_query in normalize(entry.name):
            matched.append(entry)
            continue
        if tokens and all(_stem(t) in stems for t in tokens):
            matched.append(entry)
    return matched


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

@dataclass
class ScoredProduct:
    product: object
    score: int = 0
    coverage: float = 0.0
    codes: list = field(default_factory=list)
    reasons: list = field(default_factory=list)

    def add(self, code, points, reason):
        self.score += points
        self.codes.append(code)
        self.reasons.append(reason)

    def as_match(self):
        return {
            'score': self.score,
            'coverage': round(self.coverage, 3),
            'codes': list(self.codes),
            'reasons': list(self.reasons),
        }


def _hits_in(tokens, haystack_text, haystack_tokens, variants_by_token):
    """How many query tokens appear in a haystack, and which spelling hit.

    A single-word variant is matched against the haystack's words on its stem, so
    "wick" finds "Wicks" — with a floor of three characters, so a short token
    cannot match a longer word by accident. A multi-word variant ("puja plate") is
    matched as a phrase against the whole normalised text, because it is a single
    term that happens to contain a space, not two terms.
    """
    haystack_stems = {_stem(h) for h in haystack_tokens}
    hit_variants = {}
    for token in tokens:
        for variant in variants_by_token.get(token, (token,)):
            if ' ' in variant:
                if variant in haystack_text:
                    hit_variants.setdefault(token, variant)
                    break
                continue
            stem = _stem(variant)
            if len(stem) < 3 and stem != _stem(token):
                continue
            if stem in haystack_stems:
                hit_variants.setdefault(token, variant)
                break
    return len(hit_variants), hit_variants


# Each word further into the name costs this many points. Absolute, not relative:
# normalising by name length made "Tihar Diyo Set" beat "Brass Diyo" purely because
# its name was longer, which is an artefact rather than a signal.
_POSITION_DECAY = 4


def _position_bonus(tokens, name_tokens, variants_by_token):
    """``(points, index)`` for how early the first matched token sits in the name.

    A shopper asking for "diyo" wants the lamp named "Brass Diyo", not the oil
    named "Mustard Oil for Diyo". Both contain the word, both match every token, so
    without this they score identically and popularity decides — which is exactly
    how "Cotton Wicks" came to outrank "Brass Diyo" before this module existed.
    """
    haystack_stems = [_stem(t) for t in name_tokens]
    earliest = None

    for token in tokens:
        for variant in variants_by_token.get(token, (token,)):
            # Phrases are skipped outright. Taking a phrase's first word as its
            # position reads "oil lamp" as though it were the word "oil", which
            # credited "Mustard Oil for Diyo" with an early match it never had and
            # left it ranked above "Brass Diyo". A phrase spans several words, so
            # it has no single position to score.
            if ' ' in variant:
                continue
            target = _stem(variant)
            for index, stem in enumerate(haystack_stems):
                if stem == target and (earliest is None or index < earliest):
                    earliest = index
                    break

    if earliest is None:
        return 0, 0
    return max(0, WEIGHTS['name_position'] - earliest * _POSITION_DECAY), earliest


def score_product(product, tokens, normalized_query, variants_by_token, domain_hits):
    """Score one product. Returns a :class:`ScoredProduct` with its reasons."""
    scored = ScoredProduct(product)
    if not tokens:
        return scored

    name_tokens = tokenize(product.name)
    normalized_name = normalize(product.name)
    normalized_desc = normalize(product.description or '')

    name_hits, name_variants = _hits_in(
        tokens, normalized_name, name_tokens, variants_by_token)
    desc_hits, _ = _hits_in(
        tokens, normalized_desc, tokenize(product.description or ''), variants_by_token)
    scored.coverage = name_hits / len(tokens) if tokens else 0.0

    all_name = name_hits == len(tokens)
    all_desc = desc_hits == len(tokens)

    # --- the name, best case first ---
    if all_name and normalized_name == normalized_query:
        scored.add('name_exact', WEIGHTS['name_exact'],
                   f'The name is exactly “{product.name}”')
    elif all_name and normalized_name.startswith(normalized_query):
        scored.add('name_prefix', WEIGHTS['name_prefix'],
                   f'The name starts with “{normalized_query}”')
    elif all_name:
        scored.add('name_all', WEIGHTS['name_all'],
                   _name_reason(product, tokens, name_variants))
    elif name_hits:
        points = WEIGHTS['name_partial_base'] + round(
            WEIGHTS['name_partial_span'] * scored.coverage)
        scored.add('name_partial', points,
                   _name_reason(product, tokens, name_variants))

    # --- how central the match is, among name matches only ---
    if name_hits:
        position_points, position = _position_bonus(tokens, name_tokens, variants_by_token)
        if position_points:
            scored.add('name_position', position_points,
                       f'“{product.name}” names it at word {position + 1} of '
                       f'{len(name_tokens)}')

    # --- the description, a weaker signal, only when the name did not carry it ---
    if not name_hits and desc_hits:
        if all_desc:
            scored.add('desc_all', WEIGHTS['desc_all'],
                       f'“{normalized_query}” appears in the description')
        else:
            coverage = desc_hits / len(tokens)
            points = WEIGHTS['desc_partial_base'] + round(
                WEIGHTS['desc_partial_span'] * coverage)
            scored.add('desc_partial', points,
                       'The description mentions this samagri')

    # --- the domain: is this product needed for the ritual being searched? ---
    for entry in domain_hits:
        if product.id in entry.required_product_ids:
            scored.add('domain_required', WEIGHTS['domain_required'],
                       f'Required for {entry.name} ({entry.label})')
            break
    else:
        for entry in domain_hits:
            if product.id in entry.optional_product_ids:
                scored.add('domain_optional', WEIGHTS['domain_optional'],
                           f'Optional extra for {entry.name} ({entry.label})')
                break

    return scored


def _name_reason(product, tokens, name_variants):
    """Name the spelling the catalogue actually uses when it differs from the query.

    This is the line that makes transliteration honest: a shopper who typed
    "sindur" is told the product is filed under "Sindoor", rather than silently
    getting a result and never learning the spelling the site prefers.
    """
    substitutions = {
        token: variant for token, variant in name_variants.items() if variant != token
    }
    if substitutions:
        pairs = ', '.join(f'“{query}” → “{variant}”'
                          for query, variant in sorted(substitutions.items()))
        return f'Matched {product.name} on the alternative spelling {pairs}'
    return f'“{product.name}” matches your search'


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------

def search_products(queryset, query, limit=None):
    """Rank ``queryset`` against ``query``. Returns ``(scored, meta)``.

    ``meta`` carries the query as it was understood — the expanded spellings and
    the rituals/kits it named — so the API can explain the results and the
    storefront can show "showing results for …" rather than guessing.
    """
    normalized_query = normalize(query)
    tokens, expanded = expand_query(query)

    too_short = len(normalized_query) < MIN_QUERY_LENGTH or not tokens

    meta = {
        'query': query,
        'normalized_query': normalized_query,
        'tokens': tokens,
        'expanded_terms': sorted(expanded),
        'matched_domains': [],
        'suggestions': [],
        # Reported rather than inferred from an empty result set: "keep typing" and
        # "nothing matched" are different things to say to a shopper, and an empty
        # list cannot tell them apart.
        'too_short': too_short,
    }

    if too_short:
        return [], meta

    # Variants are tracked per query token, not as one flat bag, so a product has
    # to match each token in *some* spelling rather than being credited for one
    # token's variant twice.
    variants_by_token = {}
    for token in tokens:
        if token in STOPWORDS:
            variants_by_token[token] = (token,)
            continue
        variants_by_token[token] = tuple(sorted(expand_token(token)))

    domain_hits = match_domains(tokens, normalized_query, build_domain_index())
    meta['matched_domains'] = [
        {'kind': e.kind, 'name': e.name, 'ref': e.ref} for e in domain_hits
    ]

    # Narrow in the database before scoring in Python. The catalogue is 35 products
    # so scoring everything would also work, but the candidate filter keeps the
    # Python pass proportional to the number of plausible matches rather than to
    # the size of the catalogue.
    domain_product_ids = set()
    for entry in domain_hits:
        domain_product_ids |= entry.required_product_ids | entry.optional_product_ids

    condition = _text_condition(expanded, tokens)
    if domain_product_ids:
        # The domain hits are what make "pasni" return anything at all: none of its
        # samagri has "pasni" in the name, so they have to be pulled in explicitly.
        condition |= Q(id__in=sorted(domain_product_ids))

    candidates = queryset.filter(condition).select_related('category', 'vendor')

    scored = []
    for product in candidates:
        result = score_product(
            product, tokens, normalized_query, variants_by_token, domain_hits)
        if result.score > 0:
            scored.append(result)

    scored.sort(key=lambda s: (-s.score, -s.product.popularity_score, s.product.name))
    if limit is not None:
        scored = scored[:limit]

    if not scored:
        meta['suggestions'] = suggest(query)

    return scored, meta


def _text_condition(expanded, tokens):
    """A ``Q`` matching products containing any spelling of any query token.

    ``expanded`` holds every spelling; the raw tokens are OR-ed in as well, because
    a token dropped from expansion (a stopword, or one too short to expand) would
    otherwise never reach the candidate set.
    """
    condition = Q()
    for term in sorted(expanded | set(tokens)):
        condition |= Q(name__icontains=term) | Q(description__icontains=term)
    return condition


def suggest(query, limit=3):
    """Close spellings for a query that found nothing.

    Drawn from the catalogue's own vocabulary plus every synonym group, so the
    suggestions are always words this shop can actually find. ``difflib`` is
    stdlib, deterministic, and good enough for "did you mean" — a fuzzy-match
    library would be a dependency for a feature nobody grades.
    """
    from difflib import get_close_matches

    normalized = normalize(query)
    if not normalized:
        return []

    vocabulary = set(SYNONYMS)
    for product in Product.objects.filter(is_active=True).only('name'):
        vocabulary.update(tokenize(product.name))
    vocabulary -= STOPWORDS
    vocabulary = {v for v in vocabulary if len(v) > 2}

    return get_close_matches(normalized, sorted(vocabulary), n=limit, cutoff=0.7)
