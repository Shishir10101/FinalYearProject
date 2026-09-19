# Database Design

**Engine:** SQLite (`backend/db.sqlite3`)
**Migrations applied:** see `python manage.py showmigrations`

This document describes the schema **as it actually exists in the code**, not as
it was originally planned. Every model listed here was verified against
`django.apps.apps.get_models()`.

---

## 1. Design principles applied

1. **Additive-only changes.** Every Day 1–3 migration either adds a table, adds a
   nullable column, or backfills data. No column has been dropped and no table
   renamed, so pre-existing rows (8 orders, 20 order items, 35 products) survived
   intact.
2. **Reuse before invent.** `Area` replaced a hardcoded `CITY_CHOICES` enum that
   was duplicated in `accounts` and `orders` — but the seeded `slug` values are
   byte-identical to the old enum values (`kathmandu`, `lalitpur`, `bhaktapur`),
   so existing `Order.shipping_city` values still resolve. No data rewrite needed.
3. **Nullable FKs for new relations.** `Product.vendor` is `null=True,
   on_delete=SET_NULL`. 23 of 35 products legitimately have no vendor; making the
   field required would have broken them.
4. **Denormalise deliberately.** `OrderItem.product_name` and `OrderItem.price`
   are snapshots taken at purchase time. An order must not change its historical
   total because a product was later renamed or repriced.

---

## 2. Entity-relationship overview

```
                     ┌──────────────┐
                     │     User     │  (django.contrib.auth)
                     └──────┬───────┘
                            │ 1:1
                     ┌──────▼───────┐
                     │ UserProfile  │  role ∈ {super_admin, admin, vendor, customer}
                     └──────────────┘
                            │ 1:1 (vendors only)
                     ┌──────▼───────┐        ┌──────────┐
                     │    Vendor    │───────▶│   Area   │
                     └──────┬───────┘  FK    └──────────┘
                            │ 1:N                    ▲
                     ┌──────▼───────┐                │ FK
                     │   Product    │────────────────┘  (via Vendor.area)
                     └───┬──────┬───┘
                         │      │
              FK         │      │  FK
        ┌────────────────▼┐   ┌─▼────────────┐
        │    Category      │   │  KitItem     │
        └──────────────────┘   └──────┬───────┘
                                      │ FK
                               ┌──────▼────────┐
                               │  FestivalKit  │
                               └───────────────┘

        ┌──────────┐        ┌───────────┐       ┌────────────┐
        │   Cart   │        │   Order   │──────▶│ OrderItem  │
        └──────────┘        └───────────┘  1:N  └────────────┘

        ┌──────────────────────┐
        │ SyntheticSalesRecord │  ← SYNTHETIC. Feeds the demand forecaster only.
        └──────────────────────┘
```

---

## 3. Tables

### 3.1 `accounts` — identity and role

#### `UserProfile`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user` | FK → `User`, 1:1, CASCADE | |
| `phone` | varchar(15) | |
| `address` | text | |
| `city` | varchar(20) | Legacy enum value; matches `Area.slug` |
| `role` | varchar(20), indexed | **Authoritative role.** Default `customer` |
| `is_admin_user` | bool | **Legacy, superseded.** Kept so existing data is not lost |
| `created_at` / `updated_at` | datetime | |

**Role values:** `super_admin` · `admin` · `vendor` · `customer`

**Important — `is_admin_user` is derived, not authoritative.** `UserProfile.save()`
force-syncs it to `True` whenever `role` is an admin role. Nothing should read it
for authorization; `core.permissions.get_role()` is the single source of truth.
It remains in the schema and in the API because the Day 1 dashboard already
depended on it and removing it would have been a destructive change.

**Index:** `models.Index(fields=['role'])` — every authorization check reads this.

---

### 3.2 `products` — catalogue

#### `Area` *(added Day 3)*

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar(100) | e.g. "Kathmandu" |
| `slug` | slug, unique | Auto-generated from `name` if blank |
| `district` | varchar(50) | |
| `delivery_fee` | decimal(10,2), **nullable** | `NULL` = use the store-wide default |
| `is_active` | bool | Inactive areas disappear from checkout |
| `created_at` | datetime | |

Replaces the duplicated `CITY_CHOICES` enum. Seeded with Kathmandu, Lalitpur and
Bhaktapur at slugs that match the old enum values.

#### `Vendor` *(added Day 3)*

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user` | FK → `User`, 1:1, CASCADE | The login account |
| `shop_name` | varchar(200) | |
| `slug` | slug, unique | Auto-uniquified on collision |
| `description` / `phone` / `address` | | |
| `area` | FK → `Area`, SET_NULL, nullable | |
| `is_active` | bool | |
| `created_at` / `updated_at` | datetime | |

The 1:1 link to `User` is what makes vendor scoping enforceable: a vendor sees
only `Product` rows whose `vendor` FK points at their own row.

#### `Category`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar(100) | |
| `slug` | slug, unique | Auto-generated |
| `description` | text | |
| `image` | image, nullable | |
| `created_at` | datetime | |

10 categories currently seeded (Dhoop & Agarbatti, Tika & Sindoor, Sacred
Threads, …).

#### `Product`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar(200) | |
| `slug` | slug, unique | Auto-uniquified |
| `description` | text | |
| `price` | decimal(10,2) | |
| `stock` | positive int | Decremented inside a `transaction.atomic` block at checkout |
| `category` | FK → `Category`, CASCADE | Required |
| `vendor` | FK → `Vendor`, **SET_NULL, nullable** | *Added Day 3.* 23/35 products have no vendor |
| `image` | image, nullable | |
| `is_featured` | bool | |
| `is_active` | bool | Inactive products are hidden from the storefront |
| `popularity_score` | positive int | Drives the recommender's popularity signal |
| `unit` | varchar(50) | `piece`, `packet`, `kg`, `bundle` |
| `created_at` / `updated_at` | datetime | |

**Default ordering:** `-popularity_score, -created_at`

---

### 3.3 `orders` — cart, checkout, fulfilment

#### `Cart`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user` | FK → `User` | |
| `product` | FK → `Product` | |
| `quantity` | positive int | |
| `created_at` / `updated_at` | datetime | |

#### `Order`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `user` | FK → `User` | |
| `total_amount` | decimal(10,2) | **Includes** delivery fee |
| `delivery_fee` | decimal(10,2) | *Added Day 1.* Snapshot of the fee at order time |
| `status` | varchar(20) | `pending` → `confirmed` → `shipped` → `delivered` / `cancelled` |
| `payment_method` | varchar(20) | `cod` |
| `payment_status` | varchar(20) | `pending` / `paid` |
| `shipping_address` | text | |
| `shipping_city` | varchar(20) | Holds an `Area.slug` |
| `phone` | varchar(15) | |
| `notes` | text | |
| `created_at` / `updated_at` | datetime | |

**Why `delivery_fee` is stored rather than computed.** Before Day 1 the fee was
added in the UI but not persisted, so order #9 recorded Rs. 290 while the
checkout screen promised Rs. 390. Storing the fee as its own column makes the
discrepancy impossible and keeps historical orders correct if the fee changes.

`subtotal` is exposed as a `@property` (`total_amount - delivery_fee`), not a
column — it is always derivable.

#### `OrderItem`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `order` | FK → `Order`, CASCADE | |
| `product` | FK → `Product`, SET_NULL | |
| `product_name` | varchar | **Snapshot** at purchase time |
| `quantity` | positive int | |
| `price` | decimal(10,2) | **Snapshot** unit price |

#### `OrderStatusEvent` *(added Day 4)*

Append-only history of an order's status transitions.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `order` | FK → `Order`, CASCADE | |
| `from_status` | varchar(20) | `''` for the order's first event |
| `to_status` | varchar(20) | Indexed together with `order` + `created_at` |
| `note` | varchar(255) | e.g. `Order placed by the customer.` |
| `changed_by` | FK → `User`, SET_NULL, nullable | NULL for customer-placed events |
| `created_at` | datetime | `default=timezone.now`, **not** `auto_now_add` |

Ordering is `('created_at', 'id')` — oldest first, with `id` breaking ties so two
events written in one transaction still read back deterministically.

**Why it exists.** The order timeline used to be derived from `Order.status`.
That answers "where is my order" but never "when did it get there" — the
transitions were simply not stored, so every completed step was permanently
undated. `OrderSerializer.get_timeline()` now reads real timestamps from this
table.

**Why `default=timezone.now` and not `auto_now_add`.** `auto_now_add=True`
silently discards any value passed to the constructor. The backfill migration
(`orders/0004`) needs to stamp historical orders with their real
`Order.created_at`; with `auto_now_add` every pre-existing order would have been
dated "now". This is the same class of trap as the seed migrations that shipped a
blank slug, because historical models inside a migration have no overridden
`save()`.

**`at` may legitimately be null.** A step with no recorded event returns
`at: null` and the UI renders "not recorded". Orders placed before Day 4 have a
single backfilled event, so their earlier steps have no timestamp. Borrowing
`created_at` for them would be inventing a delivery date. The one honest
exception is `pending`: an order *was* necessarily placed at `Order.created_at`,
so that value is used when no event records it.

---

### 3.4 `festivals` — the domain differentiator

#### `FestivalKit`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar(200) | |
| `festival_type` | varchar | e.g. `dashain`, `tihar`, `shivaratri` |
| `description` | text | |
| `image` | image, nullable | |
| `discount_percent` | int | Applied to the sum of kit items |
| `is_active` | bool | |
| `created_at` / `updated_at` | datetime | |

#### `KitItem`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `kit` | FK → `FestivalKit`, CASCADE | |
| `product` | FK → `Product` | |
| `quantity` | positive int | |
| `is_required` | bool | Marks a non-substitutable item |

Powers "add a whole kit to the cart in one click" — the feature that makes this a
Puja shop rather than a generic marketplace.

#### `UpcomingFestival`

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar | |
| `festival_type` | varchar | |
| `date` | date | |
| `description` | text | |
| `is_active` | bool | |

**All 5 original rows were 90–150 days in the past** when found on Day 2, so
`/festivals/upcoming/` returned `[]` and the recommender's festival signal was
silently dead. Rebuilt by the idempotent `refresh_festivals` command, which
deactivates (never deletes) stale rows.

`/festivals/upcoming/` was also capped at a hardcoded `[:5]`, so five of the ten
active festivals could not be reached through the API at all. It is now `?limit=`
(default 5, max 50).

#### `Puja` *(added Day 6)*

The ritual entry point. `AGENTS.md` §1 requires discovery through six paths —
Product · Category · Festival · **Puja** · Samagri · Ready-made Kit — and this one
had no model, endpoint or page.

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `name` | varchar(120) | |
| `slug` | slug, UNIQUE | Uniquified in `save()` (`base`, `base-1`, …) |
| `description` | text | |
| `occasion_type` | varchar(30) | `FESTIVAL_CHOICES`, blank allowed — links a ritual to the same vocabulary kits and the calendar use |
| `is_active` | bool | |
| `created_at` | datetime | |

**Why a separate model.** `FESTIVAL_CHOICES` conflates two different things. It
holds `dashain`, `tihar` and `shivaratri`, which are **calendar festivals** that
arrive on a date, and it also holds `bratabandha`, `pasni`, `griha_pravesh` and
`shraddha`, which are **rites of passage** performed when a family needs them. Two
of the enum's own labels even end in "Puja" (`chhath` → "Chhath Puja",
`saraswati` → "Saraswati Puja").

A `Puja` is the ritual; a `FestivalKit` is one purchasable bundle that serves it.
They answer different questions — *"what does this ritual need?"* versus *"what can
I buy in one click?"* — and a ritual can exist before anyone assembles a kit for
it, which is the normal state of affairs. `Daily Puja` is exactly that case.

#### `PujaItem` *(added Day 6)*

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `puja` | FK → `Puja`, CASCADE | |
| `product` | FK → `Product`, CASCADE | `unique_together ('puja', 'product')` |
| `quantity` | positive int | |
| `is_required` | bool | Same required-samagri distinction `KitItem` makes |

Ordering is `('-is_required', 'id')` — essentials first, then a stable tiebreak so
the list is deterministic.

**Not redundant with `KitItem`.** A kit is a bundle a shop chooses to sell, and its
optional extras are a merchandising decision; a puja's list is the ritual
requirement. The seeded rituals take their lists from the project's own kit data,
so the two agree today — that is a seeding choice, not a constraint.

#### `FestivalKit.puja` *(added Day 6)*

Nullable FK → `Puja`, `SET_NULL`. Lets a sellable bundle declare which ritual it
serves. Nullable so the seven existing kits kept working untouched, and `SET_NULL`
so deleting a ritual never deletes a sellable kit.

**Seeded by a command, not a migration.** `seed_pujas` is idempotent and
non-destructive. It must be a command: products, categories and kits are created
by `seed_data`, not by any migration, so a data migration seeding puja items would
find an empty catalogue on a fresh database and quietly produce rituals with no
samagri — it would look like it worked. `seed_data` calls `seed_pujas` last.

---

### 3.5 `analytics` — demand forecasting

#### `SyntheticSalesRecord` *(added Day 2)*

| Column | Type | Notes |
|---|---|---|
| `id` | PK | |
| `product` | FK → `Product` | |
| `date` | date | |
| `units_sold` | int | |
| `is_synthetic` | bool, default `True` | ⚠️ **Every row must be `True`** |
| `festival_context` | varchar | Which festival (if any) inflated this day |
| `created_at` | datetime | |

**Unique together:** `(product, date)` — makes regeneration idempotent.

> ### ⚠️ This table contains SYNTHETIC data
>
> The 14,000 rows in this table are **generated**, not real sales. They exist so
> the forecasting pipeline can be demonstrated and evaluated. Every API response
> derived from this table carries `data_source: "synthetic"` and
> `is_synthetic: true` so the caller cannot present it as real demand.
>
> Delete it with `python manage.py generate_synthetic_sales --purge`.

---

## 4. Migration history

| App | Migration | Kind | Effect |
|---|---|---|---|
| `orders` | `0002_order_delivery_fee` | Additive column | `Order.delivery_fee`, default 0 |
| `analytics` | `0001_initial` | New table | `SyntheticSalesRecord` (app previously had no models) |
| `products` | `0002_area_vendor_product_vendor` | 2 new tables + nullable FK | `Area`, `Vendor`, `Product.vendor` |
| `accounts` | `0002_userprofile_role_*` | Additive column + index | `UserProfile.role` |
| `products` | `0003_seed_areas_and_vendor` | **Data** | Seeds 3 areas; backfills roles; creates `vendor1` + demo vendor; assigns 12 products |
| `accounts` | `0003_backfill_missing_profiles` | **Data (repair)** | Creates profiles for users that had none |

### Why `accounts/0003` exists

`products/0003` set the vendor's role with:

```python
UserProfile.objects.filter(user=vendor_user).update(role=ROLE_VENDOR)  # ← BUG
```

`vendor1` had **no `UserProfile` row at all** (3 users, 2 profiles). A
`QuerySet.update()` against a non-matching filter returns `0` and raises nothing,
so the statement silently did nothing. Without a profile, `get_role()` fell
through to the `is_staff` fallback and resolved the vendor as an **admin** —
granting full catalogue access.

`accounts/0003` repairs this with `get_or_create` plus an explicit assertion.
Both data migrations are idempotent and safe to re-run.

---

## 5. Integrity rules not enforced by the database

SQLite cannot express these; they are enforced in application code.

| Rule | Enforced in |
|---|---|
| `total_amount == subtotal + delivery_fee` | `orders/views.py` (checkout, inside `transaction.atomic`) |
| Stock never goes negative | `orders/views.py` (checked, then decremented under a transaction) |
| A vendor may only write their own products | `core/permissions.py` + `get_queryset()` scoping |
| A vendor's new product is always attributed to them | `AdminProductListCreateView.perform_create()` |
| `role` cannot be self-assigned | `UserProfileSerializer.read_only_fields` |
| Every `SyntheticSalesRecord` is flagged synthetic | `generate_synthetic_sales` command |

---

## 6. Known issues and future work

| # | Issue | Severity | Notes |
|---|---|---|---|
| 1 | SQLite under concurrent writes | P1 | Fine for a demo; production needs PostgreSQL. `transaction.atomic` covers the current traffic. |
| 2 | `shipping_city` is a bare varchar, not an FK to `Area` | P1 | Chosen deliberately: an FK migration would have required rewriting existing order rows. The values currently match `Area.slug` by convention. |
| 3 | `is_admin_user` duplication | P2 | Legacy column kept in sync by `save()`. Remove once nothing reads it. |
| 4 | `custom_user_model = auth.User` | P2 | Using Django's built-in `User` + a profile rather than a custom user model. Migrating later is painful, but changing it now would break both existing repos. |
| 5 | No `Coupon` / `Review` / `Wishlist` tables | P2 | Not in scope; noted as post-MVP. |
