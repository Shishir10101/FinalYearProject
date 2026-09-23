"""Populate demo imagery for products, categories and festival kits.

Why this exists
---------------
The seeded catalogue shipped with **five** image files, of which
``puja_product_generic.png`` was reused by most of the 35 products, all ten
categories had no image at all, and every one of the 467 KB-780 KB files was
actually JPEG data behind a ``.png`` extension. The storefront rendered the
same placeholder a dozen times over and paid ~7 MB of decode for it.

This command fetches a real, relevant, properly-sized photo per row from
**Wikimedia Commons** (freely licensed, API-based, no key) and writes it into
``MEDIA_ROOT``. Every download is:

* resized to a square 600x600 and re-encoded as JPEG q82 (~40-70 KB, versus
  ~700 KB before), which is the single biggest win for the storefront's scroll
  performance;
* recorded in ``media/IMAGE-CREDITS.md`` with its Commons title, licence and
  source page, because Commons images are CC/PD and attribution is required;

and if nothing suitable is found for a row, it falls back to a locally drawn
tile with the item's name on it. **The command never leaves a row imageless**
— a missing image is what produced the broken-image icons in the first place.

Usage::

    manage.py fetch_demo_images                 # products + categories + kits
    manage.py fetch_demo_images --only products
    manage.py fetch_demo_images --force         # re-fetch rows that already have one
    manage.py fetch_demo_images --dry-run       # resolve and report, write nothing
"""

import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.conf import settings

from PIL import Image, ImageDraw, ImageFont

from festivals.models import FestivalKit
from products.models import Category, Product

COMMONS_API = 'https://commons.wikimedia.org/w/api.php'
USER_AGENT = (
    'PujaSamagriStore-Demo/1.0 '
    '(educational coursework project; contact: local dev)'
)

TARGET = 600          # px, square
JPEG_QUALITY = 82
REQUEST_PAUSE = 0.8   # be polite to the Commons API
# Commons rate-limits anonymous API traffic and answers 429 when pushed. That
# was worth chasing down: `_api` used to swallow every error and return {}, so
# a throttled row looked exactly like "Commons has nothing for this item" and
# silently became a fallback tile. The fallback list differed between two runs
# of the same code, which is what gave it away.
MAX_RETRIES_429 = 4
BACKOFF_BASE = 2.0    # seconds; doubles each attempt

# --------------------------------------------------------------------------
# Curated search terms. One entry per seeded row, tried in order until a
# candidate downloads and decodes. Deliberately specific: a bare "lamp" on
# Commons returns Victorian engravings and PDFs.
# --------------------------------------------------------------------------
PRODUCT_TERMS = {
    'Premium Dhoop Batti (Pack of 20)': ['incense sticks', 'agarbatti burning', 'dhoop incense'],
    'Chandan Agarbatti': ['agarbatti burning', 'incense sticks burning', 'sandalwood incense'],
    'Camphor (Kapur) - 50g': ['camphor crystals', 'camphor tablets', 'kapur camphor'],
    'Loban Dhoop': ['frankincense resin', 'incense resin', 'dhoop sticks'],
    'Sindoor Powder (Red)': ['sindoor vermilion', 'vermilion powder hindu'],
    'Abir Powder (Set of 5 colors)': ['gulal colour powder', 'holi colour powder'],
    'Chandan Tika Paste': ['sandalwood paste', 'chandan sandalwood'],
    'Kumkum Powder': ['kumkum powder', 'kumkum hindu'],
    'Brass Puja Kalash': ['kalash brass pot', 'hindu kalash pot', 'kalash vessel'],
    'Copper Puja Plate (Thali)': ['puja thali plate', 'aarti thali'],
    'Brass Diyo (Oil Lamp)': ['diya oil lamp', 'oil lamp brass india'],
    'Achamani Set (Spoon & Cup)': ['puja spoon', 'hindu puja utensils', 'ritual spoon'],
    'Silver Coated Puja Bell': ['ghanta bell', 'hand bell brass', 'temple bell'],
    'Artificial Marigold Garland': ['marigold garland', 'marigold flowers'],
    'Dried Rose Petals (100g)': ['dried rose petals', 'rose petals dry'],
    'Cotton Wicks (Batti) - 100pcs': ['cotton wicks lamp', 'lamp wick cotton'],
    'Puja Naivedya Set': ['prasad offering plate', 'naivedya offering'],
    'Batasha (Sugar Drops) - 250g': ['batasha sugar', 'sugar candy drops'],
    'Dried Coconut (Nariwal)': ['coconut whole', 'coconut fruit', 'dried coconut'],
    'Supari (Betel Nut) Pack': ['areca nut betel', 'betel nut supari'],
    'Janai (Sacred Thread)': ['sacred thread upanayana', 'janeu sacred thread'],
    'Kalava (Red Thread Roll)': ['kalava', 'mauli thread', 'red sacred thread'],
    'Mauli Thread (Bundle)': ['mauli thread', 'kalava mauli'],
    'Pure Cow Ghee (250ml)': ['ghee clarified butter', 'ghee jar'],
    'Mustard Oil for Diyo (500ml)': ['mustard oil', 'mustard seeds oil'],
    'Sesame Oil (Til Oil) 250ml': ['sesame oil', 'sesame seeds'],
    'Hawan Samagri Mix (500g)': ['hawan samagri', 'homa ingredients'],
    'Dried Mango Wood (Aam Ki Lakdi)': ['firewood stack', 'firewood logs', 'wood logs stacked'],
    'Hawan Kund (Small)': ['hawan kund', 'yajna fire altar'],
    'Puja Bell (Ghanti)': ['temple bell india', 'ghanta bell hindu'],
    'Conch Shell (Shankha)': ['shankha conch', 'turbinella pyrum', 'conch shell'],
    'Rudraksha Mala': ['rudraksha mala', 'rudraksha beads necklace', 'rudraksha bracelet'],
    'Tihar Diyo Set (5 piece)': ['diya lamps diwali', 'diwali oil lamps'],
    'Shivaratri Puja Set': ['shiva lingam puja', 'shivaratri puja'],
    'Dashain Tika Set': ['dashain tika nepal', 'tika rice yoghurt nepal'],
}

CATEGORY_TERMS = {
    'Dhoop & Agarbatti': ['incense sticks burning', 'agarbatti incense'],
    'Puja Flowers & Garlands': ['marigold garland', 'flower garland temple'],
    'Tika & Sindoor': ['sindoor', 'vermilion powder'],
    'Puja Vessels': ['brass vessel', 'puja utensils'],
    'Offerings & Prasad': ['annadanam', 'temple food offering', 'prasad plate'],
    'Sacred Threads': ['sacred thread hindu', 'kalava thread'],
    'Puja Oils & Ghee': ['ghee oil lamp', 'mustard oil lamp'],
    'Hawan Samagri': ['hawan fire ritual', 'yajna homa fire'],
    'Holy Books & Accessories': ['bhagavad gita book', 'hindu scripture book'],
    'Festival Special': ['diwali festival lights', 'nepal festival celebration'],
}

KIT_TERMS = {
    'Dashain Puja Complete Kit': ['dashain nepal festival', 'dashain tika'],
    'Tihar Laxmi Puja Kit': ['tihar diwali nepal', 'laxmi puja'],
    'Maha Shivaratri Puja Kit': ['maha shivaratri', 'shivaratri temple'],
    'Bratabandha Ceremony Kit': ['upanayana ceremony', 'sacred thread ceremony'],
    'Pasni (Rice Feeding) Kit': ['annaprashan rice feeding', 'rice feeding ceremony'],
    'Griha Pravesh Kit': ['griha pravesh', 'housewarming puja'],
    'Shraddha Ceremony Kit': ['shraddha ritual', 'pitru paksha'],
}

# Fallback tile palette, from the project's own tokens in globals.css.
FALLBACK_COLORS = [
    ((196, 30, 58), (155, 24, 48)),     # primary / primary-dark
    ((212, 168, 67), (184, 144, 46)),   # secondary / secondary-dark
    ((255, 107, 53), (200, 80, 35)),    # accent
    ((45, 106, 79), (32, 78, 58)),      # success
]

# Titles that mean the search matched the *wrong kind of thing*. Commons ranks
# by its own relevance and is full of near-miss traps that a keyword check
# cannot see: "conch shell" returns **conch fritters** (a Key West fried-food
# dish), "dried coconut" returns **coconut cookies**, "chandan agarbatti"
# returns an **incense-making machine**, "camphor" returns a **chemical
# structure diagram**, "kalash" returns a **balloon**. Each of those was a real
# result on the first pass. A wrong photo misrepresents the product, so these
# are rejected outright and the row gets a drawn tile instead.
REJECT_TITLE_WORDS = (
    # wrong kind of object
    'machine', 'cookies', 'cookie', 'fritter', 'fritters', 'acid', 'structure',
    'diagram', 'formula', 'balloon', 'fanush', 'dog', 'kukur', 'stamp', 'coin',
    # scanned books / old art rather than a photograph of the object
    'engraving', 'sketch', 'drawing', 'manuscript', 'djvu', 'pdf', 'screenshot',
    'advertisement', 'cartoon',
    # a person, not a thing: "prasad" matched the writer Jaishankar Prasad
    'portrait', 'personality', 'statue of', 'bust of',
    # a generic multi-image collage page rather than one object
    'wikivers', 'collage', 'montage',
    # chemistry, not the substance itself: "benzoin resin" returned the
    # benzoin *condensation* reaction scheme
    'condensation', 'reaction', 'molecule', 'chemical',
    # the plant the object comes from, rather than the object
    'fruit', 'tree', 'plant', 'flowering',
    # petals ruined for a product shot
    'stained', 'inks',
)

_HTML_TAG = re.compile(r'<[^>]+>')


def _strip_html(value):
    return _HTML_TAG.sub('', value or '').strip()


def _api(params):
    """One GET against the Commons API, returning parsed JSON or {}.

    Retries 429 with exponential backoff rather than treating it as "no
    results" — see the note on MAX_RETRIES_429.
    """
    url = COMMONS_API + '?' + urllib.parse.urlencode(params)
    for attempt in range(MAX_RETRIES_429 + 1):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < MAX_RETRIES_429:
                retry_after = exc.headers.get('Retry-After')
                try:
                    wait = float(retry_after) if retry_after else BACKOFF_BASE * (2 ** attempt)
                except (TypeError, ValueError):
                    wait = BACKOFF_BASE * (2 ** attempt)
                time.sleep(min(wait, 30.0))
                continue
            return {}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            return {}
    return {}


def _search(term, limit=8):
    """Return candidate dicts: title, thumburl, licence, artist, page."""
    data = _api({
        'action': 'query',
        'format': 'json',
        'generator': 'search',
        'gsrsearch': term,
        'gsrnamespace': '6',          # File: namespace only
        'gsrlimit': str(limit),
        'prop': 'imageinfo',
        'iiprop': 'url|mime|extmetadata',
        'iiurlwidth': str(TARGET),
    })
    pages = (data.get('query') or {}).get('pages') or {}
    out = []
    for page in pages.values():
        info = (page.get('imageinfo') or [{}])[0]
        # Commons search happily returns PDFs and DjVu scans of old books.
        if info.get('mime') not in ('image/jpeg', 'image/png'):
            continue
        if not info.get('thumburl'):
            continue
        meta = info.get('extmetadata') or {}
        out.append({
            'title': page.get('title', ''),
            'thumburl': info['thumburl'],
            'license': _strip_html((meta.get('LicenseShortName') or {}).get('value')),
            'artist': _strip_html((meta.get('Artist') or {}).get('value'))[:120],
            'page': info.get('descriptionurl', ''),
        })
    return out


def _relevant(candidate, terms):
    """Reject an obviously unrelated hit.

    Commons ranks by its own notion of relevance and will happily return a
    colonial-era travel journal for a query about lamps, conch fritters for
    "conch shell", and coconut cookies for "dried coconut". Two gates:

    1. some word of the query must actually appear in the file title, and
    2. the title must not contain a word from :data:`REJECT_TITLE_WORDS`.
    """
    title = candidate['title'].lower()
    if any(bad in title for bad in REJECT_TITLE_WORDS):
        return False
    words = set()
    for term in terms:
        words.update(w for w in re.split(r'\W+', term.lower()) if len(w) > 3)
    return any(w in title for w in words)


def _download(url, attempts=3):
    """Fetch the thumbnail bytes, retrying briefly.

    The first pass silently dropped a number of perfectly good rows because a
    single transient failure (a 429 from fetching quickly, or a timeout) made
    the candidate look unusable, and the loop moved on. Retrying turns those
    into successes instead of fallback tiles.
    """
    last_error = None
    for attempt in range(attempts):
        req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            last_error = exc
            # Thumbnails are served from a different host but throttle too.
            time.sleep(4.0 if exc.code == 429 else 0.6 * (attempt + 1))
        except Exception as exc:                     # noqa: BLE001 - retry any
            last_error = exc
            time.sleep(0.6 * (attempt + 1))
    raise last_error


def _to_square_jpeg(raw):
    """Decode, centre-crop to a square, resize, re-encode as JPEG bytes."""
    img = Image.open(io.BytesIO(raw))
    img.load()
    if img.mode in ('RGBA', 'LA', 'P'):
        # Flatten transparency onto white; the card background is light.
        background = Image.new('RGB', img.size, (255, 255, 255))
        rgba = img.convert('RGBA')
        background.paste(rgba, mask=rgba.split()[-1])
        img = background
    else:
        img = img.convert('RGB')

    width, height = img.size
    side = min(width, height)
    left = (width - side) // 2
    top = (height - side) // 2
    img = img.crop((left, top, left + side, top + side))
    if side > TARGET:
        img = img.resize((TARGET, TARGET), Image.LANCZOS)

    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


def _font(size):
    for name in ('arial.ttf', 'segoeui.ttf', 'DejaVuSans-Bold.ttf', 'calibri.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _fallback_tile(label, index):
    """Draw a branded tile carrying the item's name.

    Used only when Commons has nothing usable. Deliberately plain: a legible
    named tile is honest, whereas a stock photo of the wrong object is not.
    """
    top, bottom = FALLBACK_COLORS[index % len(FALLBACK_COLORS)]
    img = Image.new('RGB', (TARGET, TARGET), top)
    draw = ImageDraw.Draw(img)
    for y in range(TARGET):                      # vertical gradient
        ratio = y / (TARGET - 1)
        draw.line(
            [(0, y), (TARGET, y)],
            fill=tuple(int(top[c] + (bottom[c] - top[c]) * ratio) for c in range(3)),
        )

    # Wrap the label into at most four lines that fit the tile.
    words = label.split()
    lines, current = [], ''
    font = _font(44)
    for word in words:
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=font) <= TARGET - 80 or not current:
            current = trial
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:4]
    while len(lines) > 1 and max(draw.textlength(l, font=font) for l in lines) > TARGET - 80:
        font = _font(max(20, font.size - 4))

    line_height = font.size + 8
    total = len(lines) * line_height
    y = (TARGET - total) // 2
    for line in lines:
        width = draw.textlength(line, font=font)
        draw.text(((TARGET - width) / 2, y), line, font=font, fill=(255, 255, 255))
        y += line_height
    buffer = io.BytesIO()
    img.save(buffer, format='JPEG', quality=JPEG_QUALITY, optimize=True)
    return buffer.getvalue()


class Command(BaseCommand):
    help = 'Fetch free, correctly-sized demo imagery from Wikimedia Commons.'

    def add_arguments(self, parser):
        parser.add_argument('--only', choices=['products', 'categories', 'kits'],
                            help='Limit to one collection.')
        parser.add_argument('--force', action='store_true',
                            help='Re-fetch rows that already have an image.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Resolve and report, but write nothing.')
        parser.add_argument('--retry-fallbacks', action='store_true',
                            help='Re-fetch only rows currently holding a fallback '
                                 'tile (i.e. that lost to a 429), leaving real '
                                 'photos alone.')
        parser.add_argument('--match', default='',
                            help='Comma-separated substrings; re-fetch only rows '
                                 'whose name contains one of them. For correcting '
                                 'individual wrong matches without a full pass.')

    # A drawn fallback tile is 8-12 KB; the smallest real 600x600 photo here is
    # ~19 KB. The gap is wide enough to use size as the marker, which avoids
    # keeping a state file just to remember which rows fell back.
    FALLBACK_MAX_BYTES = 15 * 1024

    def _holds_fallback(self, obj):
        try:
            return obj.image.size <= self.FALLBACK_MAX_BYTES
        except (OSError, ValueError):
            return True

    def handle(self, *args, **options):
        only = options.get('only')
        force = options.get('force')
        dry_run = options.get('dry_run')
        retry_fallbacks = options.get('retry_fallbacks')
        match = [m.strip().lower() for m in (options.get('match') or '').split(',') if m.strip()]

        credits = []
        stats = {'fetched': 0, 'fallback': 0, 'skipped': 0}

        jobs = []
        if only in (None, 'products'):
            for obj in Product.objects.all().order_by('id'):
                jobs.append(('products', obj, PRODUCT_TERMS.get(obj.name, [obj.name]), obj.slug))
        if only in (None, 'categories'):
            for obj in Category.objects.all().order_by('id'):
                jobs.append(('categories', obj, CATEGORY_TERMS.get(obj.name, [obj.name]), obj.slug))
        if only in (None, 'kits'):
            for obj in FestivalKit.objects.all().order_by('id'):
                jobs.append(('kits', obj, KIT_TERMS.get(obj.name, [obj.name]), f'kit-{obj.id}'))

        for index, (kind, obj, terms, slug) in enumerate(jobs):
            has_image = bool(getattr(obj, 'image', None))
            if match and not any(m in obj.name.lower() for m in match):
                stats['skipped'] += 1
                continue
            if retry_fallbacks and not match:
                if has_image and not self._holds_fallback(obj):
                    stats['skipped'] += 1
                    continue
            elif has_image and not force and not match:
                stats['skipped'] += 1
                self.stdout.write(f'  skip   {kind[:-1]:<9} {obj.name} (already has one)')
                continue

            chosen = None
            for term in terms:
                for candidate in _search(term):
                    if not _relevant(candidate, terms):
                        continue
                    try:
                        raw = _download(candidate['thumburl'])
                        encoded = _to_square_jpeg(raw)
                    except Exception:
                        continue
                    chosen = (candidate, encoded)
                    break
                if chosen:
                    break
                time.sleep(REQUEST_PAUSE)

            if chosen:
                candidate, encoded = chosen
                stats['fetched'] += 1
                note = f"Commons: {candidate['title']}"
                credits.append({
                    'kind': kind, 'name': obj.name, 'title': candidate['title'],
                    'license': candidate['license'] or 'see source page',
                    'artist': candidate['artist'] or 'unknown',
                    'page': candidate['page'],
                })
            else:
                encoded = _fallback_tile(obj.name, index)
                stats['fallback'] += 1
                note = 'fallback tile (nothing suitable on Commons)'

            size_kb = len(encoded) / 1024
            self.stdout.write(
                f'  ok     {kind[:-1]:<9} {obj.name[:42]:<42} {size_kb:5.1f} KB  {note[:70]}'
            )

            if dry_run:
                continue

            filename = f'{slug}.jpg'
            obj.image.save(filename, ContentFile(encoded), save=True)
            time.sleep(REQUEST_PAUSE)

        if credits and not dry_run:
            self._write_credits(credits)

        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f"fetched {stats['fetched']} · fallback {stats['fallback']} · "
            f"skipped {stats['skipped']} · dry-run={dry_run}"
        ))

    def _write_credits(self, credits):
        """Write the attribution table, merging into any existing one.

        Commons images are CC/PD and require attribution, so this must survive a
        partial re-run: `--retry-fallbacks` only touches a handful of rows, and
        rewriting the file from just those would silently drop the credit for
        every photo it did not re-fetch.
        """
        path = settings.MEDIA_ROOT / 'IMAGE-CREDITS.md'
        merged = {}
        if path.exists():
            for line in path.read_text(encoding='utf-8').splitlines():
                if not line.startswith('| ') or line.startswith('| Collection'):
                    continue
                if set(line) <= set('|- '):
                    continue
                cells = [c.strip() for c in line.strip('|').split('|')]
                if len(cells) == 6:
                    merged[(cells[0], cells[1])] = cells
        for row in credits:
            merged[(row['kind'], row['name'])] = [
                row['kind'], row['name'], row['title'].replace('|', '/'),
                row['license'] or 'see source page',
                (row['artist'] or 'unknown').replace('|', '/')[:60],
                row['page'],
            ]

        lines = [
            '# Image credits',
            '',
            'Generated by `manage.py fetch_demo_images`. Images were fetched from',
            '**Wikimedia Commons** and re-encoded to 600x600 JPEG for the storefront.',
            'Each file remains under the licence of its source page, listed below.',
            'Tiles marked *fallback* were drawn locally and carry no third-party rights.',
            '',
            '| Collection | Item | Commons file | Licence | Author | Source |',
            '|---|---|---|---|---|---|',
        ]
        for key in sorted(merged):
            lines.append('| ' + ' | '.join(merged[key]) + ' |')
        lines.append('')
        path.write_text('\n'.join(lines), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'wrote {path} ({len(merged)} rows)'))
