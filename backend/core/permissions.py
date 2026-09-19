"""Role definitions and the permission classes that enforce them.

Before this module, authorization was binary and implicit:

* ``permissions.IsAdminUser`` tests Django's ``is_staff`` flag.
* ``UserProfile.is_admin_user`` existed, was set to ``True`` by the seeder, was
  exposed in the API — and was read by **no permission check anywhere**. It was
  decorative.

That is the trap this module closes. There is now an explicit, single-valued
``role`` on ``UserProfile`` and every admin-side view is gated on it.

Role hierarchy
--------------
::

    SUPER_ADMIN  →  everything, including managing admins and areas
         ↓
       ADMIN     →  catalogue, kits, orders, vendors, areas
         ↓
       VENDOR    →  only their own products and the orders containing them
         ↓
      CUSTOMER   →  own cart and own orders

Design rules
------------
1. **Additive, not destructive.** ``IsAdminUser`` behaviour is preserved for
   anyone flagged ``is_staff`` so no existing flow breaks. The new classes layer
   *additional* restrictions on top.
2. **Fail closed.** An unauthenticated request gets 401; an authenticated but
   unauthorised one gets 403. Never 200.
3. **Role is server-owned.** ``role`` is read-only in every serializer, so a
   customer cannot PATCH themselves into an admin.
4. **Vendor scoping is enforced in the queryset, not the UI.** A vendor who
   crafts a request for another vendor's product gets a 404, not a 200.
"""

from rest_framework import permissions


# ---------------------------------------------------------------------------
# Role identifiers
# ---------------------------------------------------------------------------

ROLE_SUPER_ADMIN = 'super_admin'
ROLE_ADMIN = 'admin'
ROLE_VENDOR = 'vendor'
ROLE_CUSTOMER = 'customer'

ROLE_CHOICES = [
    (ROLE_SUPER_ADMIN, 'Super Admin'),
    (ROLE_ADMIN, 'Admin'),
    (ROLE_VENDOR, 'Vendor'),
    (ROLE_CUSTOMER, 'Customer'),
]

# Roles that may reach the admin dashboard at all.
STAFF_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_VENDOR}

# Roles with full catalogue/order management.
MANAGER_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN}


def get_role(user):
    """Resolve a user's effective role.

    Precedence, highest first:

    1. ``user.is_superuser`` → ``SUPER_ADMIN``. An explicit Django superuser
       should never be demoted by a stale profile row.
    2. ``profile.role``, when set to anything other than the model default.
       This is the authoritative value and **must** beat the ``is_staff``
       fallback — a vendor is a staff user (so they can reach the dashboard) but
       must resolve as ``VENDOR``, not ``ADMIN``. Getting this order wrong gave
       vendors full catalogue access; there is a regression test for it.
    3. ``user.is_staff`` → ``ADMIN``, for legacy rows created before roles
       existed. Removing this would lock existing staff out.
    4. otherwise ``CUSTOMER``.
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return None

    if getattr(user, 'is_superuser', False):
        return ROLE_SUPER_ADMIN

    profile = getattr(user, 'profile', None)
    explicit = getattr(profile, 'role', None) if profile else None
    if explicit and explicit != ROLE_CUSTOMER:
        return explicit

    if getattr(user, 'is_staff', False):
        return ROLE_ADMIN

    return ROLE_CUSTOMER


def is_staff_role(user):
    return get_role(user) in STAFF_ROLES


def is_manager(user):
    return get_role(user) in MANAGER_ROLES


def is_super_admin(user):
    return get_role(user) == ROLE_SUPER_ADMIN


def is_vendor(user):
    return get_role(user) == ROLE_VENDOR


def vendor_for(user):
    """Return the ``Vendor`` row owned by ``user``, or ``None``."""
    if not user or not getattr(user, 'is_authenticated', False):
        return None
    from products.models import Vendor  # local import avoids a circular import

    return Vendor.objects.filter(user=user).first()


# ---------------------------------------------------------------------------
# Permission classes
# ---------------------------------------------------------------------------

class IsStaffRole(permissions.BasePermission):
    """Super Admin, Admin, or Vendor. The entry requirement for the dashboard."""

    message = 'You do not have permission to access the admin area.'

    def has_permission(self, request, view):
        return is_staff_role(request.user)


class IsManagerOrReadOnly(permissions.BasePermission):
    """Managers may write; vendors may read the shared catalogue.

    Vendors legitimately need to browse the full catalogue and existing kits to
    know what to stock. They must not be able to edit it.
    """

    message = 'Only an administrator can modify this.'

    def has_permission(self, request, view):
        if not is_staff_role(request.user):
            return False
        if request.method in permissions.SAFE_METHODS:
            return True
        return is_manager(request.user)


class IsSuperAdmin(permissions.BasePermission):
    """Reserved for actions that change who can administer the system."""

    message = 'Only a Super Admin can perform this action.'

    def has_permission(self, request, view):
        return is_super_admin(request.user)


class IsOwnerVendorOrManager(permissions.BasePermission):
    """Object-level check: a vendor may only touch their own products.

    Managers pass unconditionally. A vendor must own the object. Anyone with a
    staff role attempting to reach someone else's object gets 403, and the
    queryset also filters it out so the common path returns 404 rather than
    leaking the object's existence.
    """

    message = 'This product belongs to another vendor.'

    def has_object_permission(self, request, view, obj):
        if is_manager(request.user):
            return True
        if not is_vendor(request.user):
            return False
        vendor = vendor_for(request.user)
        if vendor is None:
            return False
        # ``Product`` carries ``vendor``; other models reach it via ``product``.
        obj_vendor = getattr(obj, 'vendor', None)
        if obj_vendor is None:
            product = getattr(obj, 'product', None)
            obj_vendor = getattr(product, 'vendor', None)
        return obj_vendor == vendor
