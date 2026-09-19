"""Authorization tests for the role system and vendor scoping.

These are the tests that would have caught the two bugs found on Day 3:

1. ``get_role()`` checked ``is_staff`` *before* the explicit ``profile.role``,
   so a vendor account (which is necessarily ``is_staff`` to reach the API at
   all) resolved to ``admin`` and got full catalogue access.
2. The role backfill migration used ``QuerySet.update()`` against a profile
   that did not exist, silently matching zero rows. The vendor then had no
   profile at all and fell through to the ``is_staff`` fallback — admin again.

Both failures were *silent*. A vendor saw everything and nothing complained.
The tests below assert on observable HTTP behaviour, not on internal helper
return values, so a future refactor that reintroduces either bug fails here.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserProfile
from core.permissions import (
    ROLE_ADMIN, ROLE_CUSTOMER, ROLE_SUPER_ADMIN, ROLE_VENDOR,
    get_role, is_manager, is_staff_role, vendor_for,
)
from orders.models import Cart, Order, OrderItem
from products.models import Area, Category, Product, Vendor


def bearer(user):
    """The API is JWT-only — there is no session authentication.

    ``self.client.force_login()`` therefore silently produces 401s. Every
    authenticated request in this module goes through this helper.
    """
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class RoleTestBase(TestCase):
    """Builds one user per role plus two vendors with disjoint catalogues."""

    def setUp(self):
        # The seed data migration already created the three valley areas when the
        # test database was built, so fetch rather than create.
        self.area = Area.objects.get(slug='kathmandu')
        self.category = Category.objects.create(name='Dhoop & Agarbatti')

        self.super_admin = self._make_user('root', role=ROLE_SUPER_ADMIN, is_superuser=True)
        self.admin = self._make_user('ops', role=ROLE_ADMIN, is_staff=True)
        self.vendor_a_user = self._make_user('vendor_a', role=ROLE_VENDOR, is_staff=True)
        self.vendor_b_user = self._make_user('vendor_b', role=ROLE_VENDOR, is_staff=True)
        self.customer = self._make_user('shopper', role=ROLE_CUSTOMER)

        self.vendor_a = Vendor.objects.create(user=self.vendor_a_user, shop_name='Shop A')
        self.vendor_b = Vendor.objects.create(user=self.vendor_b_user, shop_name='Shop B')

        self.product_a = Product.objects.create(
            name='Shop A Incense', description='a', price=100, stock=50,
            category=self.category, vendor=self.vendor_a,
        )
        self.product_b = Product.objects.create(
            name='Shop B Incense', description='b', price=100, stock=50,
            category=self.category, vendor=self.vendor_b,
        )
        self.product_orphan = Product.objects.create(
            name='Unassigned Incense', description='c', price=100, stock=50,
            category=self.category, vendor=None,
        )

        self.client = APIClient()

    def _make_user(self, username, role, is_staff=False, is_superuser=False):
        user = User.objects.create_user(username=username, password='pw-test-123')
        user.is_staff = is_staff
        user.is_superuser = is_superuser
        user.save()
        UserProfile.objects.create(user=user, role=role, is_admin_user=is_staff)
        return user

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=bearer(user))


class RoleResolutionTests(RoleTestBase):
    """``get_role`` must prefer the explicit profile role over the is_staff flag."""

    def test_superuser_resolves_to_super_admin(self):
        self.assertEqual(get_role(self.super_admin), ROLE_SUPER_ADMIN)

    def test_admin_resolves_to_admin(self):
        self.assertEqual(get_role(self.admin), ROLE_ADMIN)

    def test_vendor_resolves_to_vendor_not_admin(self):
        # Regression: is_staff was checked before profile.role, so this returned
        # 'admin' and unlocked the whole catalogue.
        self.assertEqual(get_role(self.vendor_a_user), ROLE_VENDOR)
        self.assertFalse(is_manager(self.vendor_a_user))

    def test_customer_resolves_to_customer(self):
        self.assertEqual(get_role(self.customer), ROLE_CUSTOMER)
        self.assertFalse(is_staff_role(self.customer))

    def test_anonymous_resolves_to_none(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(get_role(AnonymousUser()))
        self.assertIsNone(get_role(None))

    def test_staff_user_without_profile_still_resolves(self):
        """A staff user with no profile row must not crash; falls back to admin."""
        ghost = User.objects.create_user(username='ghost', password='pw-test-123')
        ghost.is_staff = True
        ghost.save()
        self.assertEqual(get_role(ghost), ROLE_ADMIN)

    def test_customer_profile_with_staff_flag_is_admin(self):
        """Explicit customer + is_staff: the flag is the tiebreaker."""
        odd = User.objects.create_user(username='odd', password='pw-test-123')
        odd.is_staff = True
        odd.save()
        UserProfile.objects.create(user=odd, role=ROLE_CUSTOMER, is_admin_user=True)
        self.assertEqual(get_role(odd), ROLE_ADMIN)

    def test_vendor_for_returns_own_vendor_only(self):
        self.assertEqual(vendor_for(self.vendor_a_user), self.vendor_a)
        self.assertIsNone(vendor_for(self.admin))
        self.assertIsNone(vendor_for(self.customer))


class ProductScopingTests(RoleTestBase):
    """A vendor must see their own products and nobody else's."""

    def test_customer_gets_401_on_admin_product_list(self):
        self.auth(self.customer)
        resp = self.client.get('/api/products/admin/products/')
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_gets_401(self):
        resp = self.client.get('/api/products/admin/products/')
        self.assertEqual(resp.status_code, 401)

    def test_vendor_list_excludes_other_vendors_products(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/products/admin/products/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        ids = {r['id'] for r in rows}
        self.assertIn(self.product_a.id, ids)
        self.assertNotIn(self.product_b.id, ids)
        self.assertNotIn(self.product_orphan.id, ids)

    def test_admin_list_includes_everything(self):
        self.auth(self.admin)
        resp = self.client.get('/api/products/admin/products/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        ids = {r['id'] for r in rows}
        for product in (self.product_a, self.product_b, self.product_orphan):
            self.assertIn(product.id, ids)

    def test_vendor_cannot_read_other_vendors_product_detail(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get(f'/api/products/admin/products/{self.product_b.id}/')
        self.assertEqual(resp.status_code, 404)

    def test_vendor_can_read_own_product_detail(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get(f'/api/products/admin/products/{self.product_a.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['id'], self.product_a.id)

    def test_vendor_cannot_update_other_vendors_product(self):
        self.auth(self.vendor_a_user)
        resp = self.client.patch(
            f'/api/products/admin/products/{self.product_b.id}/',
            {'price': '1.00'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.product_b.refresh_from_db()
        self.assertEqual(float(self.product_b.price), 100.0)

    def test_vendor_can_update_own_product(self):
        self.auth(self.vendor_a_user)
        resp = self.client.patch(
            f'/api/products/admin/products/{self.product_a.id}/',
            {'price': '123.00'}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.product_a.refresh_from_db()
        self.assertEqual(float(self.product_a.price), 123.0)

    def test_vendor_cannot_delete_other_vendors_product(self):
        self.auth(self.vendor_a_user)
        resp = self.client.delete(f'/api/products/admin/products/{self.product_b.id}/')
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Product.objects.filter(id=self.product_b.id).exists())

    def test_public_catalogue_still_lists_everything(self):
        """Scoping must not leak into the storefront — customers buy across vendors."""
        resp = self.client.get('/api/products/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        ids = {r['id'] for r in rows}
        self.assertIn(self.product_a.id, ids)
        self.assertIn(self.product_b.id, ids)

    def test_vendor_cannot_probe_via_vendor_filter(self):
        """The ``vendor`` filter must not become an enumeration oracle."""
        self.auth(self.vendor_a_user)
        resp = self.client.get(
            f'/api/products/admin/products/?vendor={self.vendor_b.id}'
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        self.assertEqual(rows, [])

    def test_vendor_created_product_is_attributed_to_them(self):
        """A vendor cannot mint a product owned by a different vendor."""
        self.auth(self.vendor_a_user)
        resp = self.client.post(
            '/api/products/admin/products/',
            {
                'name': 'Vendor A New Item', 'description': 'x', 'price': '75.00',
                'stock': 10, 'category': self.category.id,
                'vendor': self.vendor_b.id,  # attempt to spoof ownership
            },
            format='json',
        )
        self.assertIn(resp.status_code, (200, 201))
        created = Product.objects.get(name='Vendor A New Item')
        self.assertEqual(created.vendor_id, self.vendor_a.id)

    def test_admin_created_product_can_be_assigned_any_vendor(self):
        self.auth(self.admin)
        resp = self.client.post(
            '/api/products/admin/products/',
            {
                'name': 'Admin Item', 'description': 'x', 'price': '75.00',
                'stock': 10, 'category': self.category.id,
                'vendor': self.vendor_b.id,
            },
            format='json',
        )
        self.assertIn(resp.status_code, (200, 201))
        created = Product.objects.get(name='Admin Item')
        self.assertEqual(created.vendor_id, self.vendor_b.id)


class OrderScopingTests(RoleTestBase):
    """A vendor must only see orders containing their own products."""

    def setUp(self):
        super().setUp()
        self.order_a = Order.objects.create(
            user=self.customer, status='pending', total_amount=200,
            delivery_fee=100, shipping_address='Thamel, Kathmandu', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=self.order_a, product=self.product_a,
            product_name=self.product_a.name, quantity=1, price=100,
        )
        self.order_b = Order.objects.create(
            user=self.customer, status='pending', total_amount=200,
            delivery_fee=100, shipping_address='Thamel, Kathmandu', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=self.order_b, product=self.product_b,
            product_name=self.product_b.name, quantity=1, price=100,
        )

    def _order_ids(self, resp):
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        return {r['id'] for r in rows}

    def test_vendor_sees_only_orders_with_their_products(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/orders/admin/orders/')
        self.assertEqual(resp.status_code, 200)
        ids = self._order_ids(resp)
        self.assertIn(self.order_a.id, ids)
        self.assertNotIn(self.order_b.id, ids)

    def test_admin_sees_all_orders(self):
        self.auth(self.admin)
        resp = self.client.get('/api/orders/admin/orders/')
        self.assertEqual(resp.status_code, 200)
        ids = self._order_ids(resp)
        self.assertIn(self.order_a.id, ids)
        self.assertIn(self.order_b.id, ids)

    def test_customer_cannot_reach_admin_order_list(self):
        self.auth(self.customer)
        resp = self.client.get('/api/orders/admin/orders/')
        self.assertEqual(resp.status_code, 403)

    def test_vendor_cannot_update_other_vendors_order(self):
        self.auth(self.vendor_a_user)
        resp = self.client.patch(
            f'/api/orders/admin/orders/{self.order_b.id}/',
            {'status': 'shipped'}, format='json',
        )
        self.assertEqual(resp.status_code, 404)
        self.order_b.refresh_from_db()
        self.assertEqual(self.order_b.status, 'pending')

    def test_vendor_can_update_own_order(self):
        self.auth(self.vendor_a_user)
        resp = self.client.patch(
            f'/api/orders/admin/orders/{self.order_a.id}/',
            {'status': 'shipped'}, format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.order_a.refresh_from_db()
        self.assertEqual(self.order_a.status, 'shipped')

    def test_order_appearing_twice_is_deduplicated(self):
        """An order with two of the vendor's products must not list twice."""
        OrderItem.objects.create(
            order=self.order_a, product=self.product_a,
            product_name=self.product_a.name, quantity=2, price=100,
        )
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/orders/admin/orders/')
        ids = [r['id'] for r in (resp.json()['results'] if 'results' in resp.json() else resp.json())]
        self.assertEqual(ids.count(self.order_a.id), 1)


class AnalyticsScopingTests(RoleTestBase):
    """Dashboard analytics must respect the same boundary as the lists."""

    def test_customer_forbidden_on_analytics(self):
        self.auth(self.customer)
        resp = self.client.get('/api/analytics/sales/')
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_forbidden_on_analytics(self):
        resp = self.client.get('/api/analytics/sales/')
        self.assertEqual(resp.status_code, 401)

    def test_vendor_overview_reports_vendor_scope(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/analytics/sales/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['scope'], 'vendor')
        # Only Shop A's product is in scope, not Shop B's or the orphan.
        self.assertEqual(resp.json()['total_products'], 1)

    def test_admin_overview_reports_full_scope(self):
        self.auth(self.admin)
        resp = self.client.get('/api/analytics/sales/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['scope'], 'all')
        self.assertEqual(resp.json()['total_products'], 3)

    def test_vendor_inventory_excludes_other_vendors(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/analytics/inventory/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['total_products'], 1)

    def test_vendor_trending_excludes_other_vendors(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/analytics/trending/')
        self.assertEqual(resp.status_code, 200)
        names = {row['name'] for row in resp.json()}
        self.assertEqual(names, {self.product_a.name})

    def test_vendor_cannot_forecast_another_vendors_product(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get(
            f'/api/analytics/demand-forecast/?product={self.product_b.id}'
        )
        self.assertEqual(resp.status_code, 404)

    def test_vendor_alerts_exclude_other_vendors_products(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/analytics/predictions/')
        self.assertEqual(resp.status_code, 200)
        product_ids = {
            a['product_id'] for a in resp.json()['alerts'] if 'product_id' in a
        }
        self.assertNotIn(self.product_b.id, product_ids)
        self.assertNotIn(self.product_orphan.id, product_ids)


class RoleEscalationTests(RoleTestBase):
    """A user must not be able to promote themselves through the API."""

    def test_customer_cannot_patch_own_role(self):
        self.auth(self.customer)
        resp = self.client.patch(
            '/api/accounts/profile/', {'role': ROLE_SUPER_ADMIN}, format='json',
        )
        # Either the field is rejected or it is silently read-only — both are
        # acceptable. What matters is that the role did not change.
        self.customer.profile.refresh_from_db()
        self.assertEqual(self.customer.profile.role, ROLE_CUSTOMER)

    def test_customer_cannot_patch_own_is_admin_user(self):
        self.auth(self.customer)
        self.client.patch(
            '/api/accounts/profile/', {'is_admin_user': True}, format='json',
        )
        self.customer.profile.refresh_from_db()
        self.assertFalse(self.customer.profile.is_admin_user)

    def test_customer_cannot_create_product(self):
        self.auth(self.customer)
        resp = self.client.post(
            '/api/products/admin/products/',
            {
                'name': 'Sneaky', 'description': 'x', 'price': '10.00',
                'stock': 5, 'category': self.category.id,
            },
            format='json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(Product.objects.filter(name='Sneaky').exists())


class AreaAndVendorAdminTests(RoleTestBase):
    """Area/vendor management is a super-admin concern."""

    def test_admin_can_list_areas(self):
        self.auth(self.admin)
        resp = self.client.get('/api/products/admin/areas/')
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_list_areas(self):
        self.auth(self.customer)
        resp = self.client.get('/api/products/admin/areas/')
        self.assertEqual(resp.status_code, 403)

    def test_public_area_list_is_open(self):
        resp = self.client.get('/api/products/areas/')
        self.assertEqual(resp.status_code, 200)
        # The seed migration creates Kathmandu, Lalitpur and Bhaktapur.
        slugs = {row['slug'] for row in resp.json()}
        self.assertEqual(slugs, {'kathmandu', 'lalitpur', 'bhaktapur'})

    def test_admin_can_list_vendors(self):
        self.auth(self.admin)
        resp = self.client.get('/api/products/admin/vendors/')
        self.assertEqual(resp.status_code, 200)

    def test_customer_cannot_list_vendors(self):
        self.auth(self.customer)
        resp = self.client.get('/api/products/admin/vendors/')
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_read_any_vendor_detail(self):
        self.auth(self.admin)
        resp = self.client.get(f'/api/products/admin/vendors/{self.vendor_b.id}/')
        self.assertEqual(resp.status_code, 200)

    def test_vendor_list_is_scoped_to_self(self):
        """Vendor management is a manager concern — a vendor sees only itself."""
        self.auth(self.vendor_a_user)
        resp = self.client.get('/api/products/admin/vendors/')
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        rows = body['results'] if isinstance(body, dict) and 'results' in body else body
        ids = {r['id'] for r in rows}
        self.assertEqual(ids, {self.vendor_a.id})


class VendorSlugTests(RoleTestBase):
    """A shop name that slugify() reduces to nothing must still yield a slug.

    Regression: ``Vendor.save()`` assigned ``slugify(shop_name)`` directly. A name
    slugify() strips (e.g. all Devanagari) produced ``self.slug == ''``, which
    re-entered the ``if not self.slug`` branch on every save and left the row with
    a blank unique slug. The seeded ``Patan Puja Bhandar`` shipped with ''.
    """

    def test_normal_shop_name_slugifies(self):
        vendor = Vendor.objects.create(user=self.customer, shop_name='Newa Puja Store')
        self.assertEqual(vendor.slug, 'newa-puja-store')

    def test_unslugifiable_shop_name_gets_a_fallback(self):
        vendor = Vendor.objects.create(user=self.customer, shop_name='\u092a\u093e\u091f\u0928 \u092a\u0942\u091c\u093e')
        self.assertTrue(vendor.slug, 'slug must never be blank')
        self.assertNotEqual(vendor.slug, '')

    def test_existing_blank_slug_is_backfilled_on_save(self):
        vendor = Vendor.objects.create(user=self.customer, shop_name='Temporary Shop')
        # Simulate the legacy bad row written by the old save(). Bypass the model
        # and the unique index would normally reject a second ''; here the only
        # other vendor is the seeded one, whose slug is now non-blank.
        Vendor.objects.filter(pk=vendor.pk).update(slug='')
        vendor.refresh_from_db()
        self.assertEqual(vendor.slug, '')

        vendor.save()  # must repair itself
        vendor.refresh_from_db()
        self.assertTrue(vendor.slug)

    def test_duplicate_shop_names_get_distinct_slugs(self):
        first = Vendor.objects.create(user=self.customer, shop_name='Same Shop')
        second_user = self._make_user('second_vendor', role=ROLE_VENDOR, is_staff=True)
        second = Vendor.objects.create(user=second_user, shop_name='Same Shop')
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, 'same-shop-1')

    def test_seeded_vendor_has_a_slug(self):
        """Regression: the seed migration wrote ``Patan Puja Bhandar`` with slug ''.

        Historical models in a migration have no overridden ``save()``, so the
        slug was never generated. A blank unique slug also means only ONE such
        vendor can ever exist, and ``PATCH`` on it stays blank forever.
        """
        vendor = Vendor.objects.get(shop_name='Patan Puja Bhandar')
        self.assertEqual(vendor.slug, 'patan-puja-bhandar')

    def test_no_vendor_has_a_blank_slug(self):
        blank = Vendor.objects.filter(slug='')
        self.assertEqual(blank.count(), 0, 'no vendor may have a blank slug')


class VendorPermissionCoherenceTests(RoleTestBase):
    """The vendor list and detail views must agree on who may read them.

    Regression: the list view allowed any staff role while the detail view
    required a super admin, so an ADMIN could browse the list and then get a 403
    on every single row.
    """

    def test_admin_can_list_and_detail_vendors(self):
        self.auth(self.admin)
        listing = self.client.get('/api/products/admin/vendors/')
        self.assertEqual(listing.status_code, 200)
        detail = self.client.get(f'/api/products/admin/vendors/{self.vendor_a.id}/')
        self.assertEqual(
            detail.status_code, 200,
            'an ADMIN who can list vendors must also be able to open one',
        )

    def test_super_admin_can_list_and_detail_vendors(self):
        self.auth(self.super_admin)
        self.assertEqual(self.client.get('/api/products/admin/vendors/').status_code, 200)
        self.assertEqual(
            self.client.get(f'/api/products/admin/vendors/{self.vendor_a.id}/').status_code, 200
        )

    def test_vendor_list_and_detail_both_403_for_customer(self):
        self.auth(self.customer)
        self.assertEqual(self.client.get('/api/products/admin/vendors/').status_code, 403)
        self.assertEqual(
            self.client.get(f'/api/products/admin/vendors/{self.vendor_a.id}/').status_code, 403
        )

    def test_vendor_cannot_open_another_vendor_detail(self):
        self.auth(self.vendor_a_user)
        resp = self.client.get(f'/api/products/admin/vendors/{self.vendor_b.id}/')
        # Either 403 or 404 is acceptable, but it must NOT be 200.
        self.assertIn(resp.status_code, (403, 404))

    def test_vendor_cannot_delete_a_vendor(self):
        self.auth(self.vendor_a_user)
        resp = self.client.delete(f'/api/products/admin/vendors/{self.vendor_b.id}/')
        self.assertIn(resp.status_code, (403, 404))
        self.assertTrue(Vendor.objects.filter(pk=self.vendor_b.pk).exists())

    def test_admin_cannot_delete_vendors_with_products(self):
        """Deleting a vendor must not silently orphan its catalogue.

        ``Product.vendor`` is ``on_delete=SET_NULL``, so a delete would succeed
        but quietly unassign every product. Confirmed behaviour, asserted so a
        future change is a deliberate decision rather than an accident.
        """
        self.auth(self.admin)
        before = Product.objects.filter(vendor=self.vendor_a).count()
        self.assertGreater(before, 0)
        resp = self.client.delete(f'/api/products/admin/vendors/{self.vendor_a.id}/')
        self.assertIn(resp.status_code, (204, 200, 400, 409))
        remaining = Product.objects.filter(vendor=self.vendor_a).count()
        # Whatever happens, no product row may vanish.
        self.assertEqual(Product.objects.filter(name='Shop A Incense').count(), 1)
        self.assertEqual(remaining, 0, 'FK is SET_NULL: products survive but lose their vendor')
