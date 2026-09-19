"""Repair: the vendor created by 0003 never got a ``UserProfile``.

``0003_seed_areas_and_vendor`` created the ``vendor1`` user and then set its role
with::

    UserProfile.objects.filter(user=vendor_user).update(role='vendor', ...)

``QuerySet.update()`` returns the number of rows changed and raises nothing when
that number is zero. Because ``vendor1`` had just been created and had no profile
row, the update matched **zero rows and silently did nothing**.

The consequence was not cosmetic. With no profile, ``get_role()`` fell through to
the ``is_staff`` fallback and resolved the vendor as ``ADMIN`` — full catalogue
and order access for a role that is supposed to be scoped to its own products.

Fix: create the profile explicitly, then assert the role is actually persisted.
"""

from django.db import migrations


def forwards(apps, schema_editor):
    UserProfile = apps.get_model('accounts', 'UserProfile')
    Vendor = apps.get_model('products', 'Vendor')
    User = apps.get_model('auth', 'User')

    # 1. Every vendor must have a profile whose role is exactly ``vendor``.
    for vendor in Vendor.objects.select_related('user'):
        profile, created = UserProfile.objects.get_or_create(
            user=vendor.user,
            defaults={
                'role': 'vendor',
                'is_admin_user': False,
                'city': 'lalitpur',
                'phone': vendor.phone or '',
                'address': vendor.address or '',
            },
        )
        if not created and profile.role != 'vendor':
            profile.role = 'vendor'
            # A vendor is a staff user (needs dashboard access) but is NOT an
            # administrator, so the legacy flag must be cleared.
            profile.is_admin_user = False
            profile.save(update_fields=['role', 'is_admin_user'])

    # 2. Any remaining user without a profile gets one, so role resolution is
    #    never left to the is_staff fallback.
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


def backwards(apps, schema_editor):
    """No-op: removing profiles on rollback could lock a user out entirely."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_userprofile_role_alter_userprofile_is_admin_user_and_more'),
        ('products', '0003_seed_areas_and_vendor'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
