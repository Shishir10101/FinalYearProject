"""Backfill real areas, roles, and a demo vendor.

This migration exists because the two previous migrations were additive schema
changes. Without a data step:

* every existing user would default to ``role='customer'``, including the
  administrator — who would immediately lose access to the dashboard;
* the ``Area`` table would be empty even though ``UserProfile.city`` and
  ``Order.shipping_city`` already contain ``kathmandu``/``lalitpur``/``bhaktapur``.

Everything here is idempotent and non-destructive: it only fills in blanks and
never deletes a user, an order, or a product.

Reverse: clears the roles/areas this migration created. It is intentionally a
no-op for user data so a rollback cannot strip an administrator's access.
"""

from django.db import migrations

# Slugs match the old CITY_CHOICES values exactly, so existing
# UserProfile.city and Order.shipping_city strings keep resolving.
SEED_AREAS = [
    ('Kathmandu', 'kathmandu', 'Kathmandu'),
    ('Lalitpur', 'lalitpur', 'Lalitpur'),
    ('Bhaktapur', 'bhaktapur', 'Bhaktapur'),
]


def forwards(apps, schema_editor):
    Area = apps.get_model('products', 'Area')
    Vendor = apps.get_model('products', 'Vendor')
    Product = apps.get_model('products', 'Product')
    UserProfile = apps.get_model('accounts', 'UserProfile')
    User = apps.get_model('auth', 'User')

    # --- 1. Areas ---------------------------------------------------------
    areas = {}
    for name, slug, district in SEED_AREAS:
        area, _ = Area.objects.get_or_create(
            slug=slug,
            defaults={'name': name, 'district': district, 'is_active': True},
        )
        areas[slug] = area

    # --- 2. Roles ---------------------------------------------------------
    # Order matters: superuser first, then is_staff, then the legacy flag.
    for profile in UserProfile.objects.select_related('user'):
        user = profile.user
        if user.is_superuser:
            role = 'super_admin'
        elif user.is_staff:
            role = 'admin'
        elif profile.is_admin_user:
            role = 'admin'
        else:
            role = 'customer'

        if profile.role != role:
            profile.role = role
            # Keep the legacy flag in sync so nothing downstream regresses.
            if role in ('super_admin', 'admin'):
                profile.is_admin_user = True
            profile.save(update_fields=['role', 'is_admin_user'])

    # Users without a profile at all still need one to be resolvable.
    for user in User.objects.filter(profile__isnull=True):
        if user.is_superuser:
            role = 'super_admin'
        elif user.is_staff:
            role = 'admin'
        else:
            role = 'customer'
        UserProfile.objects.create(
            user=user, role=role,
            is_admin_user=role in ('super_admin', 'admin'),
        )

    # --- 3. Demo vendor ---------------------------------------------------
    # Gives the vendor role something real to be scoped against.
    vendor_user = User.objects.filter(username='vendor1').first()
    if vendor_user is None:
        vendor_user = User.objects.create_user(
            username='vendor1',
            email='vendor@pujasmagri.com',
            password='vendor1234',
            first_name='Sita',
            last_name='Poudel',
        )
        vendor_user.is_staff = True  # staff = may reach the dashboard
        vendor_user.save(update_fields=['is_staff'])

    UserProfile.objects.filter(user=vendor_user).update(
        role='vendor', is_admin_user=False, city='lalitpur',
        phone='9841555000', address='Patan Durbar Square, Lalitpur',
    )

    # --- 3b. Guarantee a profile exists -----------------------------------
    # ``update()`` above matches zero rows when the profile is missing, and it
    # does so *silently*. That is exactly how ``vendor1`` ended up with no
    # UserProfile and therefore resolved to ``admin``. get_or_create cannot fail
    # this way.
    UserProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            'role': 'vendor', 'is_admin_user': False, 'city': 'lalitpur',
            'phone': '9841555000', 'address': 'Patan Durbar Square, Lalitpur',
        },
    )
    # Re-assert in case the profile already existed but was stale.
    UserProfile.objects.filter(user=vendor_user).update(
        role='vendor', is_admin_user=False,
    )

    vendor, created = Vendor.objects.get_or_create(
        user=vendor_user,
        defaults={
            'shop_name': 'Patan Puja Bhandar',
            # Historical models have no overridden save(), so set the slug
            # explicitly. ``update_or_create`` also repairs a blank slug that a
            # previous run may have written.
            'slug': 'patan-puja-bhandar',
            'description': (
                'Traditional puja samagri supplier in Patan, serving the '
                'Lalitpur area since 1998.'
            ),
            'phone': '9841555000',
            'address': 'Patan Durbar Square, Lalitpur',
            'area': areas.get('lalitpur'),
            'is_active': True,
        },
    )
    Vendor.objects.filter(pk=vendor.pk, slug='').update(slug='patan-puja-bhandar')

    # --- 4. Assign a subset of products to the vendor ---------------------
    # Only catalogue items that have no vendor yet. Idempotent by construction.
    if created:
        unassigned = Product.objects.filter(vendor__isnull=True).order_by('id')
        # Give the vendor a realistic slice rather than the whole catalogue, so
        # vendor scoping is visibly *narrower* than admin access during a demo.
        for product in unassigned[:12]:
            product.vendor = vendor
            product.save(update_fields=['vendor'])


def backwards(apps, schema_editor):
    """Deliberately conservative: unassign vendors, keep areas and roles.

    Stripping roles on rollback could lock an administrator out of the system,
    which is a worse outcome than leaving a default value in place.
    """
    Product = apps.get_model('products', 'Product')
    Product.objects.update(vendor=None)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_userprofile_role_alter_userprofile_is_admin_user_and_more'),
        ('products', '0002_area_vendor_product_vendor'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
