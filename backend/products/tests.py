"""Catalogue validation tests.

These cover gaps found while wiring per-field errors into the admin dashboard.
Probing the live API for error *shapes* turned up three payloads that were
accepted when they should have been refused:

* ``price: -5``  — a negative price subtracts from the cart total.
* ``delivery_fee: -50`` on an Area — the store would pay the customer to deliver.
* a duplicate category name — silently filed as ``puja-oils-ghee-1``, splitting
  one category into two and showing both in the storefront navigation.

Each one is a data-integrity bug that no existing test covered, because the
earlier suites only exercised happy-path CRUD.

Run with::

    python manage.py test products -v 2
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserProfile
from core.permissions import ROLE_ADMIN
from .models import Area, Category, Product


def bearer(user):
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class CatalogueValidationTestBase(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            'ops', password='pw12345678', is_staff=True, is_superuser=True,
        )
        UserProfile.objects.create(user=self.admin, role=ROLE_ADMIN)

        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))

        self.category = Category.objects.create(name='Validation Category')
        self.area = Area.objects.get(slug='kathmandu')

    def product_payload(self, **overrides):
        payload = {
            'name': 'Validation Product',
            'description': 'x',
            'price': '100',
            'stock': 5,
            'category': self.category.id,
            'unit': 'piece',
        }
        payload.update(overrides)
        return payload


class PriceValidationTests(CatalogueValidationTestBase):
    def test_negative_price_is_rejected(self):
        response = self.client.post(
            '/api/products/admin/products/',
            self.product_payload(price='-5'), format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('price', response.json())

    def test_negative_price_is_not_created(self):
        before = Product.objects.count()
        self.client.post('/api/products/admin/products/',
                         self.product_payload(price='-0.01'), format='json')
        self.assertEqual(Product.objects.count(), before)

    def test_zero_price_is_allowed(self):
        """A free item (prasad, a complimentary item) is legitimate."""
        response = self.client.post('/api/products/admin/products/',
                                    self.product_payload(price='0'), format='json')
        self.assertEqual(response.status_code, 201, response.json())

    def test_positive_price_is_allowed(self):
        response = self.client.post('/api/products/admin/products/',
                                    self.product_payload(price='249.50'), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Decimal(response.json()['price']), Decimal('249.50'))

    def test_model_validator_also_blocks_negative_price(self):
        """Protects the Django admin and shell paths, not just the API."""
        from django.core.exceptions import ValidationError

        product = Product(name='Bad', description='x', price=Decimal('-1'),
                          category=self.category)
        with self.assertRaises(ValidationError):
            product.full_clean()


class DeliveryFeeValidationTests(CatalogueValidationTestBase):
    def test_negative_delivery_fee_is_rejected(self):
        response = self.client.post('/api/products/admin/areas/',
                                    {'name': 'Negative Fee Area', 'delivery_fee': '-50'},
                                    format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('delivery_fee', response.json())

    def test_negative_delivery_fee_creates_no_area(self):
        before = Area.objects.count()
        self.client.post('/api/products/admin/areas/',
                         {'name': 'Negative Fee Area', 'delivery_fee': '-1'}, format='json')
        self.assertEqual(Area.objects.count(), before)

    def test_zero_delivery_fee_is_allowed(self):
        """Free delivery inside a specific area is a real business rule."""
        response = self.client.post('/api/products/admin/areas/',
                                    {'name': 'Free Delivery Zone', 'delivery_fee': '0'},
                                    format='json')
        self.assertEqual(response.status_code, 201, response.json())
        Area.objects.filter(name='Free Delivery Zone').delete()

    def test_blank_delivery_fee_still_means_use_the_default(self):
        response = self.client.post('/api/products/admin/areas/',
                                    {'name': 'Default Fee Zone', 'delivery_fee': None},
                                    format='json')
        self.assertEqual(response.status_code, 201, response.json())
        self.assertIsNone(response.json()['delivery_fee'])
        Area.objects.filter(name='Default Fee Zone').delete()


class CategoryNameValidationTests(CatalogueValidationTestBase):
    def test_duplicate_name_is_rejected_case_insensitively(self):
        response = self.client.post('/api/products/admin/categories/',
                                    {'name': 'validation category'}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json())

    def test_duplicate_does_not_create_a_suffixed_row(self):
        """The old behaviour filed a second row as `validation-category-1`."""
        self.client.post('/api/products/admin/categories/',
                         {'name': 'Validation Category'}, format='json')
        self.assertEqual(Category.objects.filter(name__iexact='Validation Category').count(), 1)

    def test_a_genuinely_new_name_is_accepted(self):
        response = self.client.post('/api/products/admin/categories/',
                                    {'name': 'A Brand New Category'}, format='json')
        self.assertEqual(response.status_code, 201, response.json())

    def test_renaming_a_category_to_its_own_name_is_allowed(self):
        """Editing without touching the name must not collide with itself."""
        response = self.client.patch(
            f'/api/products/admin/categories/{self.category.id}/',
            {'name': 'Validation Category', 'description': 'updated'}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.json())

    def test_renaming_onto_another_category_is_rejected(self):
        other = Category.objects.create(name='Another Category')
        response = self.client.patch(
            f'/api/products/admin/categories/{other.id}/',
            {'name': 'Validation Category'}, format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json())

    def test_blank_name_is_rejected(self):
        response = self.client.post('/api/products/admin/categories/',
                                    {'name': '   '}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('name', response.json())


class SlugUniquifierStillWorksTests(CatalogueValidationTestBase):
    """The name check is the real guard; the suffixer must remain as a fallback.

    The suffixer exists because a duplicate slug raised an unhandled
    ``IntegrityError`` (HTTP 500). Removing it in favour of the name check alone
    would reintroduce that crash for any path the check does not cover, such as
    two Devanagari names that slugify to the same string.
    """

    def test_model_still_uniquifies_slugs_on_collision(self):
        first = Category.objects.create(name='Slug Collision Probe')
        second = Category.objects.create(name='Slug Collision Probe')
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(second.slug, 'slug-collision-probe-1')

    def test_area_slugs_still_uniquify(self):
        first = Area.objects.create(name='Area Collision Probe')
        second = Area.objects.create(name='Area Collision Probe')
        self.assertNotEqual(first.slug, second.slug)
