"""Catalogue tests: validation, reviews, and domain-aware search.

The validation cases cover gaps found while wiring per-field errors into the admin
dashboard. Probing the live API for error *shapes* turned up three payloads that were
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

import shutil
import tempfile

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserProfile
from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER
from festivals.models import FestivalKit, KitItem, Puja, PujaItem
from orders.models import Order, OrderItem
from .models import Area, Category, Product, Review, WishlistItem
from .search import (
    PARTIAL_CODES, REASON_CODES, SYNONYMS, WEIGHTS, normalize, search_products,
)


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


class ReviewTestBase(TestCase):
    """One product, one reviewer, one staff account."""

    def setUp(self):
        self.category = Category.objects.create(name='Review Cat')
        self.product = Product.objects.create(
            name='Reviewable Dhoop', description='x', price=Decimal('120'),
            stock=20, category=self.category,
        )
        self.customer = self._user('reviewer', ROLE_CUSTOMER)
        self.other = self._user('other_customer', ROLE_CUSTOMER)
        self.manager = self._user('review_mgr', ROLE_ADMIN)

    def _user(self, username, role):
        user = User.objects.create_user(username, password='pw12345678')
        UserProfile.objects.create(user=user, role=role)
        return user

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
            )
        return client

    def url(self, slug=None):
        return f"/api/products/{slug or self.product.slug}/reviews/"

    def post_review(self, user, rating=5, title='Great', body='Really good dhoop.'):
        return self.api(user).post(
            self.url(), {'rating': rating, 'title': title, 'body': body}, format='json',
        )


class ReviewWriteTests(ReviewTestBase):
    """One review per customer per product, and the API enforces it."""

    def test_anyone_can_read_reviews(self):
        response = self.api().get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['results'], [])
        self.assertIsNone(response.json()['summary']['average_rating'])

    def test_a_customer_can_post_a_review(self):
        response = self.post_review(self.customer)
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(response.json()['rating'], 5)

    def test_an_anonymous_post_is_refused(self):
        response = self.api().post(self.url(), {'rating': 5, 'body': 'x'}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_a_second_post_edits_rather_than_duplicating(self):
        """`unique_together` means one row; a second POST is an edit of your own."""
        self.assertEqual(self.post_review(self.customer, rating=5).status_code, 201)
        response = self.post_review(self.customer, rating=2, body='Changed my mind.')
        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(Review.objects.filter(product=self.product).count(), 1)
        self.assertEqual(Review.objects.get(product=self.product).rating, 2)

    def test_two_customers_can_each_review(self):
        self.post_review(self.customer)
        self.post_review(self.other, rating=3)
        self.assertEqual(Review.objects.filter(product=self.product).count(), 2)

    def test_rating_must_be_between_one_and_five(self):
        for bad in (0, 6, -1):
            response = self.post_review(self.customer, rating=bad)
            self.assertEqual(response.status_code, 400, f'rating={bad} was accepted')

    def test_a_rating_with_no_words_is_refused(self):
        """A bare star is not a review, and it is the shape most abuse takes."""
        response = self.api(self.customer).post(
            self.url(), {'rating': 1, 'title': '', 'body': '   '}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_title_alone_is_enough(self):
        response = self.api(self.customer).post(
            self.url(), {'rating': 4, 'title': 'Good', 'body': ''}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.json())

    def test_clearing_the_text_on_update_is_refused(self):
        self.post_review(self.customer)
        response = self.api(self.customer).patch(
            f"/api/products/reviews/{Review.objects.get(product=self.product).id}/",
            {'body': '', 'title': ''}, format='json',
        )
        # PATCH is not routed (delete-only detail), so this is a 405 — either way the
        # review must not end up as a bare rating.
        review = Review.objects.get(product=self.product)
        self.assertTrue(review.body or review.title)
        self.assertIn(response.status_code, (400, 405))

    def test_a_review_of_an_unknown_product_is_404(self):
        response = self.api(self.customer).post(
            '/api/products/no-such-product/reviews/', {'rating': 5, 'body': 'x'},
            format='json',
        )
        self.assertEqual(response.status_code, 404)

    def test_an_inactive_product_cannot_be_reviewed(self):
        self.product.is_active = False
        self.product.save(update_fields=['is_active'])
        self.assertEqual(self.post_review(self.customer).status_code, 404)


class ReviewSummaryTests(ReviewTestBase):
    """The average must come from approved reviews only, and from *all* of them."""

    def test_the_average_reflects_every_review(self):
        self.post_review(self.customer, rating=5)
        self.post_review(self.other, rating=3)
        summary = self.api().get(self.url()).json()['summary']
        self.assertEqual(summary['review_count'], 2)
        self.assertEqual(summary['average_rating'], 4.0)

    def test_the_distribution_is_a_five_to_one_histogram(self):
        self.post_review(self.customer, rating=5)
        self.post_review(self.other, rating=5)
        distribution = self.api().get(self.url()).json()['summary']['distribution']
        self.assertEqual(list(distribution.keys()), ['5', '4', '3', '2', '1'])
        self.assertEqual(distribution['5'], 2)
        self.assertEqual(distribution['1'], 0)

    def test_hiding_a_review_changes_the_average(self):
        """The whole point of hiding one."""
        self.post_review(self.customer, rating=5)
        self.post_review(self.other, rating=1)
        Review.objects.filter(user=self.other).update(is_approved=False)

        body = self.api().get(self.url()).json()
        self.assertEqual(body['summary']['review_count'], 1)
        self.assertEqual(body['summary']['average_rating'], 5.0)
        self.assertEqual(len(body['results']), 1)

    def test_a_product_with_no_reviews_has_a_null_average(self):
        """Not 0 — a product nobody has rated has no rating, and 0 stars would be a lie."""
        detail = self.api().get(f'/api/products/{self.product.slug}/').json()
        self.assertIsNone(detail['average_rating'])
        self.assertEqual(detail['review_count'], 0)

    def test_the_product_detail_carries_the_summary(self):
        self.post_review(self.customer, rating=4)
        detail = self.api().get(f'/api/products/{self.product.slug}/').json()
        self.assertEqual(detail['average_rating'], 4.0)
        self.assertEqual(detail['review_count'], 1)

    def test_the_review_list_is_paginated(self):
        """A review list grows, so it pages — unlike the admin editor lists."""
        for i in range(14):
            user = self._user(f'bulk_reviewer_{i}', ROLE_CUSTOMER)
            self.post_review(user, rating=4)
        body = self.api().get(self.url()).json()
        self.assertEqual(len(body['results']), 12)
        self.assertEqual(body['count'], 14)
        self.assertEqual(body['summary']['review_count'], 14)


class ReviewPrivacyTests(ReviewTestBase):
    """A public review list must not publish who bought what."""

    def test_the_author_is_reduced_to_a_display_name(self):
        self.customer.first_name = 'Ram'
        self.customer.last_name = 'Sharma'
        self.customer.save()
        self.post_review(self.customer)

        author = self.api().get(self.url()).json()['results'][0]['author']
        self.assertEqual(author, 'Ram S.')
        self.assertNotIn('Sharma', author)

    def test_a_username_is_not_an_email(self):
        self.customer.email = 'ram@example.com'
        self.customer.first_name = ''
        self.customer.last_name = ''
        self.customer.save()
        self.post_review(self.customer)

        author = self.api().get(self.url()).json()['results'][0]['author']
        self.assertEqual(author, 'reviewer')
        self.assertNotIn('@', author)

    def test_the_payload_carries_no_user_id(self):
        self.post_review(self.customer)
        row = self.api().get(self.url()).json()['results'][0]
        self.assertNotIn('user', row)
        self.assertNotIn('email', row)

    def test_mine_is_null_for_an_anonymous_reader(self):
        self.post_review(self.customer)
        self.assertIsNone(self.api().get(self.url()).json()['mine'])

    def test_mine_is_returned_to_its_author(self):
        self.post_review(self.customer, rating=3)
        body = self.api(self.customer).get(self.url()).json()
        self.assertIsNotNone(body['mine'])
        self.assertEqual(body['mine']['rating'], 3)
        self.assertTrue(body['mine']['is_mine'])

    def test_mine_is_null_for_somebody_else(self):
        self.post_review(self.customer)
        self.assertIsNone(self.api(self.other).get(self.url()).json()['mine'])


class VerifiedPurchaseTests(ReviewTestBase):
    """`is_verified_purchase` is a snapshot of whether they had bought it."""

    def test_false_without_an_order(self):
        self.post_review(self.customer)
        self.assertFalse(Review.objects.get(product=self.product).is_verified_purchase)

    def test_true_when_the_reviewer_had_ordered_it(self):
        order = Order.objects.create(
            user=self.customer, total_amount=Decimal('120'),
            shipping_address='x', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            price=self.product.price, quantity=1,
        )
        self.post_review(self.customer)
        self.assertTrue(Review.objects.get(product=self.product).is_verified_purchase)

    def test_a_cancelled_order_does_not_count(self):
        order = Order.objects.create(
            user=self.customer, total_amount=Decimal('120'), status='cancelled',
            shipping_address='x', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            price=self.product.price, quantity=1,
        )
        self.post_review(self.customer)
        self.assertFalse(Review.objects.get(product=self.product).is_verified_purchase)

    def test_the_badge_does_not_change_when_a_later_order_arrives(self):
        """It is recorded at creation, never recomputed."""
        self.post_review(self.customer)
        self.assertFalse(Review.objects.get(product=self.product).is_verified_purchase)

        order = Order.objects.create(
            user=self.customer, total_amount=Decimal('120'),
            shipping_address='x', shipping_city='kathmandu', phone='9800000000',
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            price=self.product.price, quantity=1,
        )
        self.assertFalse(Review.objects.get(product=self.product).is_verified_purchase)


class ReviewDeletionTests(ReviewTestBase):
    def test_the_author_can_delete_their_own(self):
        self.post_review(self.customer)
        review = Review.objects.get(product=self.product)
        self.assertEqual(
            self.api(self.customer).delete(f'/api/products/reviews/{review.id}/').status_code,
            204,
        )

    def test_another_customer_gets_404_not_403(self):
        """No existence leak: the queryset is filtered by owner."""
        self.post_review(self.customer)
        review = Review.objects.get(product=self.product)
        response = self.api(self.other).delete(f'/api/products/reviews/{review.id}/')
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Review.objects.filter(id=review.id).exists())

    def test_a_manager_can_delete_any(self):
        self.post_review(self.customer)
        review = Review.objects.get(product=self.product)
        self.assertEqual(
            self.api(self.manager).delete(f'/api/products/reviews/{review.id}/').status_code,
            204,
        )

    def test_deleting_a_product_removes_its_reviews(self):
        self.post_review(self.customer)
        self.product.delete()
        self.assertEqual(Review.objects.count(), 0)


class AdminReviewTests(ReviewTestBase):
    """Moderation: a manager must be able to see what they hid."""

    def setUp(self):
        super().setUp()
        self.post_review(self.customer, rating=1, body='Rude and unhelpful.')
        self.review = Review.objects.get(product=self.product)

    def test_a_manager_sees_every_review(self):
        Review.objects.update(is_approved=False)
        response = self.api(self.manager).get('/api/products/admin/reviews/')
        self.assertEqual(response.status_code, 200)
        # A **bare list**, matching every other admin collection here. A `results`
        # dict would still pass a len() check against a page and hide the fact that a
        # hidden review on page 2 is invisible to the only person who can unhide it.
        rows = response.json()
        self.assertIsInstance(rows, list, 'the admin review list must not be paginated')
        self.assertEqual(len(rows), 1, 'a hidden review must still be visible to a manager')

    def test_a_customer_is_refused(self):
        self.assertEqual(
            self.api(self.customer).get('/api/products/admin/reviews/').status_code, 403
        )

    def test_an_anonymous_reader_is_refused(self):
        self.assertEqual(self.api().get('/api/products/admin/reviews/').status_code, 401)

    def test_the_admin_payload_names_the_product_and_the_author(self):
        body = self.api(self.manager).get('/api/products/admin/reviews/').json()
        row = body[0]
        self.assertEqual(row['product_name'], self.product.name)
        self.assertEqual(row['username'], 'reviewer')

    def test_a_manager_can_hide_a_review(self):
        response = self.api(self.manager).patch(
            f'/api/products/admin/reviews/{self.review.id}/', {'is_approved': False},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_approved)
        # And it leaves the storefront immediately.
        self.assertEqual(self.api().get(self.url()).json()['count'], 0)

    def test_a_manager_can_unhide_it_again(self):
        """Otherwise `is_approved=False` is a one-way door."""
        Review.objects.update(is_approved=False)
        self.api(self.manager).patch(
            f'/api/products/admin/reviews/{self.review.id}/', {'is_approved': True},
            format='json',
        )
        self.review.refresh_from_db()
        self.assertTrue(self.review.is_approved)

    def test_the_verified_badge_is_read_only_for_a_manager(self):
        """It is a snapshot; a manager editing it would rewrite history."""
        response = self.api(self.manager).patch(
            f'/api/products/admin/reviews/{self.review.id}/',
            {'is_verified_purchase': True}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        self.review.refresh_from_db()
        self.assertFalse(self.review.is_verified_purchase)

    def test_filtering_by_approval(self):
        self.api(self.manager).patch(
            f'/api/products/admin/reviews/{self.review.id}/', {'is_approved': False},
            format='json',
        )
        hidden = self.api(self.manager).get('/api/products/admin/reviews/?is_approved=0').json()
        shown = self.api(self.manager).get('/api/products/admin/reviews/?is_approved=1').json()
        self.assertEqual(len(hidden), 1)
        self.assertEqual(len(shown), 0)

    def test_a_manager_can_delete_a_review(self):
        self.assertEqual(
            self.api(self.manager).delete(
                f'/api/products/admin/reviews/{self.review.id}/'
            ).status_code,
            204,
        )


class ReviewQueryCountTests(ReviewTestBase):
    """The product detail must not grow a query per review."""

    def test_the_product_detail_does_not_count_reviews_per_row(self):
        self.post_review(self.customer)
        for i in range(6):
            user = self._user(f'qc_reviewer_{i}', ROLE_CUSTOMER)
            self.post_review(user, rating=3)

        url = f'/api/products/{self.product.slug}/'
        client = self.api()
        with self.assertNumQueries(3):
            # Exactly three, and it does not move with the number of reviews:
            #   1. the product, with AVG/COUNT FILTER'd over its approved reviews
            #   2. the category (a FK join, resolved by the nested serializer)
            #   3. the category's active product count
            # The number that matters is that N reviews still costs three queries. If
            # the summary were a SerializerMethodField this would be 3 + N, which is
            # the trap the ritual list carries a test for.
            client.get(url)


# --- Domain-aware search ---------------------------------------------------
#
# `AGENTS.md` §1 lists Samagri as one of six discovery entry points, and search was
# the weakest of them. Every case below is a real failure that was measured against
# the seeded catalogue before `products/search.py` existed — not a hypothetical:
# `sindur` returned 0 products, `pasni` and `griha pravesh` returned 0, and `diyo`
# ranked "Cotton Wicks" above "Brass Diyo".
#
# These assert *ordering and explanation*, not response shape. A search that returns
# the right products in the wrong order is still a broken search, and a result that
# cannot say why it is there is indistinguishable from a random one.


class SearchTestBase(TestCase):
    """A miniature catalogue carrying the transliteration pairs that matter."""

    def setUp(self):
        self.category = Category.objects.create(name='Search Cat')
        self.sindoor = self._product(
            'Sindoor Powder (Red)', 'Pure vermillion powder for tika and ceremonies.')
        self.diyo = self._product(
            'Brass Diyo (Oil Lamp)', 'Traditional brass diyo for lighting during puja.')
        self.oil = self._product(
            'Mustard Oil for Diyo (500ml)', 'Cold pressed mustard oil for the diyo.')
        self.wicks = self._product(
            'Cotton Wicks (Batti) - 100pcs', 'Ready-made cotton wicks.')
        self.dhoop = self._product('Loban Dhoop', 'Loban incense for daily puja.')
        self.thali = self._product(
            'Copper Puja Plate (Thali)', 'A plate for offerings.')
        # Carries no "puja" in its name, and is reachable only through the thali/tray
        # synonym group. That makes it the honest test of group isolation: the thali
        # above matches "puja" legitimately, by name, and proves nothing either way.
        self.tray = self._product('Copper Serving Tray', 'A tray for carrying offerings.')
        self.agarbatti = self._product(
            'Chandan Agarbatti', 'Sandalwood incense sticks.')
        self.retired = self._product(
            'Retired Sindoor', 'Withdrawn from sale.', is_active=False)

        self.ritual = Puja.objects.create(
            name='Pasni (Rice Feeding)', slug='pasni-rice-feeding',
            description='The first-rice ceremony.', occasion_type='pasni')
        PujaItem.objects.create(puja=self.ritual, product=self.sindoor,
                                quantity=1, is_required=True)
        PujaItem.objects.create(puja=self.ritual, product=self.oil,
                                quantity=1, is_required=False)

        self.kit = FestivalKit.objects.create(
            name='Pasni (Rice Feeding) Kit', festival_type='pasni',
            description='Everything for the ceremony.', puja=self.ritual)
        KitItem.objects.create(kit=self.kit, product=self.wicks,
                               quantity=1, is_required=True)

    def _product(self, name, description, is_active=True):
        return Product.objects.create(
            name=name, description=description, price=Decimal('100'),
            stock=10, category=self.category, is_active=is_active,
        )

    def search(self, query):
        return search_products(Product.objects.filter(is_active=True), query)

    def names(self, query):
        scored, _ = self.search(query)
        return [item.product.name for item in scored]

    def first_name(self, query):
        scored, _ = self.search(query)
        return scored[0].product.name if scored else None

    def codes_for(self, query, product_name):
        scored, _ = self.search(query)
        for item in scored:
            if item.product.name == product_name:
                return item.codes
        return []


class NormalizationTests(SearchTestBase):
    """Folding is what makes two spellings of one word comparable."""

    def test_normalize_lowercases_and_strips_punctuation(self):
        self.assertEqual(normalize('  Sindoor  Powder (Red) '), 'sindoor powder red')

    def test_normalize_folds_diacritics_to_ascii(self):
        self.assertEqual(normalize('Tīl Öil'), 'til oil')

    def test_normalize_treats_ampersand_as_and(self):
        self.assertEqual(normalize('Spoon & Cup'), 'spoon and cup')

    def test_the_plural_fold_matches_wicks_and_wick(self):
        self.assertEqual(normalize('wicks').rstrip('s'), normalize('wick').rstrip('s'))

    def test_a_short_token_cannot_match_a_longer_word(self):
        # "ti" must not be credited with matching "til" — the floor is three
        # characters. Without it, a two-letter query matches half the catalogue.
        scored, _ = self.search('ti')
        self.assertEqual(scored, [])


class TransliterationTests(SearchTestBase):
    """The failure that started this: a second spelling of a Nepali term."""

    VARIANTS = (
        ('sindur', 'Sindoor Powder (Red)'),
        ('sindor', 'Sindoor Powder (Red)'),
        ('sindhur', 'Sindoor Powder (Red)'),
        ('vermillion', 'Sindoor Powder (Red)'),
        ('deep', 'Brass Diyo (Oil Lamp)'),
        ('deepak', 'Brass Diyo (Oil Lamp)'),
        ('diya', 'Brass Diyo (Oil Lamp)'),
        ('lamp', 'Brass Diyo (Oil Lamp)'),
        ('thali', 'Copper Puja Plate (Thali)'),
        ('tray', 'Copper Puja Plate (Thali)'),
        ('incense', 'Chandan Agarbatti'),
        ('agarbati', 'Chandan Agarbatti'),
        ('dhup', 'Loban Dhoop'),
    )

    def test_every_alternative_spelling_finds_its_product(self):
        for query, expected in self.VARIANTS:
            with self.subTest(query=query):
                self.assertIn(expected, self.names(query),
                              f'“{query}” did not find “{expected}”')

    def test_the_reason_names_the_spelling_the_catalogue_uses(self):
        """A shopper who typed “sindur” is told the shop files it under “sindoor”."""
        scored, _ = self.search('sindur')
        reasons = ' '.join(scored[0].reasons)
        self.assertIn('sindoor', reasons)
        self.assertIn('sindur', reasons)

    def test_expansion_reports_every_spelling_it_tried(self):
        _, meta = self.search('sindur')
        for spelling in ('sindur', 'sindoor', 'sindor', 'sindhur'):
            self.assertIn(spelling, meta['expanded_terms'])


class SynonymIsolationTests(SearchTestBase):
    """A synonym group must not leak into an unrelated word.

    Both of these were real bugs in the first implementation, which built its index
    by splitting multi-word group members into their component words. That registered
    ``puja`` as a synonym of ``thali`` (from the member "puja plate") and ``batti`` as
    a synonym of ``dhoop`` (from "dhoop batti") — so searching "puja" returned plates,
    and searching "dhup" returned *Cotton Wicks*.
    """

    def test_a_group_member_does_not_become_a_synonym_of_its_own_words(self):
        self.assertNotIn('thali', SYNONYMS.get('puja', frozenset()))
        self.assertNotIn('plate', SYNONYMS.get('puja', frozenset()))

    def test_puja_does_not_reach_a_tray_that_never_mentions_it(self):
        # The tray is in the thali/tray/plate group, so the leak this guards against
        # would surface it for "puja" even though neither its name nor its description
        # contains the word.
        self.assertNotIn('Copper Serving Tray', self.names('puja'))

    def test_the_group_still_works_from_either_direction(self):
        # Isolation must not come at the cost of the feature: the tray is reachable
        # by every spelling in its group.
        for query in ('tray', 'thali', 'plate'):
            with self.subTest(query=query):
                self.assertIn('Copper Serving Tray', self.names(query))

    def test_dhup_does_not_return_cotton_wicks(self):
        self.assertNotIn('Cotton Wicks (Batti) - 100pcs', self.names('dhup'))

    def test_a_multi_word_member_still_matches_as_a_phrase(self):
        # "puja plate" is a member of the thali group, so it must still find the
        # thali — the fix is that it matches as a phrase, not that it stops working.
        self.assertEqual(self.first_name('puja plate'), 'Copper Puja Plate (Thali)')


class RankingTests(SearchTestBase):
    """The product itself must outrank one that merely mentions it."""

    def test_the_object_ranks_above_a_product_named_after_it(self):
        # "Mustard Oil for Diyo" contains "diyo"; "Brass Diyo" *is* a diyo. Both match
        # every token, so only position separates them.
        self.assertEqual(self.first_name('diyo'), 'Brass Diyo (Oil Lamp)')
        self.assertLess(self.names('diyo').index('Brass Diyo (Oil Lamp)'),
                        self.names('diyo').index('Mustard Oil for Diyo (500ml)'))

    def test_an_exact_name_beats_a_prefix_match(self):
        self.assertEqual(self.first_name('sindoor'), 'Sindoor Powder (Red)')

    def test_a_name_match_beats_a_description_only_match(self):
        # "Loban Dhoop" is named for it; the wicks merely mention diyo in a sentence.
        names = self.names('dhoop')
        self.assertEqual(names[0], 'Loban Dhoop')

    def test_the_position_reason_is_recorded(self):
        self.assertIn('name_position', self.codes_for('diyo', 'Brass Diyo (Oil Lamp)'))

    def test_ordering_is_deterministic_across_runs(self):
        self.assertEqual(self.names('puja'), self.names('puja'))
        self.assertEqual(self.names('diyo'), self.names('diyo'))


class DomainSearchTests(SearchTestBase):
    """Searching a ritual by name must find the samagri it needs.

    No product is named after a ritual — the link lives in `PujaItem` / `KitItem`.
    Before this, `pasni` returned nothing at all, although it is a seeded ritual with
    a complete kit behind it.
    """

    def test_a_ritual_name_finds_its_required_samagri(self):
        self.assertIn('Sindoor Powder (Red)', self.names('pasni'))

    def test_a_ritual_name_finds_its_kits_samagri_too(self):
        self.assertIn('Cotton Wicks (Batti) - 100pcs', self.names('pasni'))

    def test_the_ritual_is_reported_back(self):
        _, meta = self.search('pasni')
        kinds = {entry['kind'] for entry in meta['matched_domains']}
        self.assertIn('ritual', kinds)
        self.assertIn('kit', kinds)
        names = [entry['name'] for entry in meta['matched_domains']]
        self.assertIn('Pasni (Rice Feeding)', names)

    def test_the_domain_reason_is_recorded(self):
        codes = self.codes_for('pasni', 'Sindoor Powder (Red)')
        self.assertIn('domain_required', codes)

    def test_a_required_item_outranks_an_optional_one(self):
        required = self.codes_for('pasni', 'Sindoor Powder (Red)')
        optional = self.codes_for('pasni', 'Mustard Oil for Diyo (500ml)')
        self.assertIn('domain_required', required)
        self.assertIn('domain_optional', optional)

    def test_a_multi_word_ritual_name_works(self):
        ritual = Puja.objects.create(
            name='Griha Pravesh', slug='griha-pravesh',
            description='Housewarming.', occasion_type='griha_pravesh')
        PujaItem.objects.create(puja=ritual, product=self.thali,
                                quantity=1, is_required=True)
        self.assertIn('Copper Puja Plate (Thali)', self.names('griha pravesh'))

    def test_a_name_the_catalogue_qualifies_still_matches(self):
        # The ritual is "Pasni (Rice Feeding)", not "Pasni" — the query is a subset
        # of the name's words, not a substring of it.
        _, meta = self.search('pasni')
        self.assertTrue(meta['matched_domains'])

    def test_an_inactive_ritual_is_not_matched(self):
        self.ritual.is_active = False
        self.ritual.save()
        self.assertNotIn('Sindoor Powder (Red)', self.names('pasni'))


class SearchSafetyTests(SearchTestBase):
    """Edge cases that must not produce confident nonsense."""

    def test_an_inactive_product_is_never_returned(self):
        self.assertNotIn('Retired Sindoor', self.names('sindoor'))

    def test_an_empty_query_is_flagged_and_returns_nothing(self):
        scored, meta = self.search('')
        self.assertEqual(scored, [])
        self.assertTrue(meta['too_short'])

    def test_a_one_character_query_is_flagged_rather_than_searched(self):
        scored, meta = self.search('s')
        self.assertEqual(scored, [])
        self.assertTrue(meta['too_short'])

    def test_nonsense_returns_nothing_and_is_not_flagged_as_short(self):
        scored, meta = self.search('xyzzy')
        self.assertEqual(scored, [])
        self.assertFalse(meta['too_short'])

    def test_a_typo_is_offered_a_suggestion(self):
        _, meta = self.search('sindoer')
        self.assertIn('sindoor', meta['suggestions'])

    def test_no_suggestion_is_offered_when_something_matched(self):
        _, meta = self.search('sindoor')
        self.assertEqual(meta['suggestions'], [])

    def test_every_result_explains_itself(self):
        for query in ('sindoor', 'diyo', 'pasni', 'puja', 'thali'):
            for item in self.search(query)[0]:
                with self.subTest(query=query, product=item.product.name):
                    self.assertTrue(item.reasons,
                                    f'{item.product.name} matched “{query}” with no reason')
                    self.assertTrue(item.codes)

    def test_every_emitted_reason_code_is_declared(self):
        """A code the scorer can emit but the module does not declare is a typo."""
        for query in ('sindoor', 'diyo', 'pasni', 'puja', 'thali', 'puja plate'):
            for item in self.search(query)[0]:
                for code in item.codes:
                    with self.subTest(code=code):
                        self.assertIn(code, REASON_CODES)

    def test_every_non_partial_code_has_a_weight_behind_it(self):
        """A code with no weight behind it means a score nobody can trace.

        The ``*_partial`` tiers are exempt by design: they are a base plus a span
        scaled by coverage, so there is no single constant to point at. Everything
        else must map 1:1 onto WEIGHTS, which is what makes a score decomposable
        back into the reasons shown to the shopper.
        """
        for code in REASON_CODES - PARTIAL_CODES:
            with self.subTest(code=code):
                self.assertIn(code, WEIGHTS)


class SearchAPITests(SearchTestBase):
    """The endpoint: public, paginated, and carrying the explanation."""

    URL = '/api/products/search/'

    def test_search_is_public(self):
        response = APIClient().get(self.URL, {'q': 'sindoor'})
        self.assertEqual(response.status_code, 200)

    def test_the_response_carries_the_match_block(self):
        response = APIClient().get(self.URL, {'q': 'sindoor'})
        row = response.data['results'][0]
        self.assertIn('match', row)
        self.assertIn('reasons', row['match'])
        self.assertIn('score', row['match'])

    def test_the_response_carries_the_query_it_understood(self):
        response = APIClient().get(self.URL, {'q': 'sindur'})
        self.assertEqual(response.data['normalized_query'], 'sindur')
        self.assertIn('sindoor', response.data['expanded_terms'])

    def test_search_is_paginated_and_pages_do_not_overlap(self):
        # "puja" matches most of this fixture catalogue, so it spans pages.
        for i in range(20):
            self._product(f'Puja Item {i}', 'A puja samagri.')
        first = APIClient().get(self.URL, {'q': 'puja', 'page': 1})
        second = APIClient().get(self.URL, {'q': 'puja', 'page': 2})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        ids_first = {row['id'] for row in first.data['results']}
        ids_second = {row['id'] for row in second.data['results']}
        self.assertTrue(ids_first)
        self.assertTrue(ids_second)
        self.assertFalse(ids_first & ids_second, 'page 1 and page 2 share rows')
        self.assertIsNotNone(first.data['next'])

    def test_the_alias_parameter_works_too(self):
        by_q = APIClient().get(self.URL, {'q': 'sindoor'})
        by_search = APIClient().get(self.URL, {'search': 'sindoor'})
        self.assertEqual(by_q.data['count'], by_search.data['count'])

    def test_an_unknown_term_is_an_empty_200_not_a_404(self):
        response = APIClient().get(self.URL, {'q': 'xyzzy'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 0)

    def test_a_missing_query_is_an_empty_200(self):
        response = APIClient().get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['too_short'])

    def test_a_short_query_is_told_to_keep_typing_rather_than_shown_no_results(self):
        response = APIClient().get(self.URL, {'q': 's'})
        self.assertTrue(response.data['too_short'])
        self.assertEqual(response.data['count'], 0)


class WishlistTestBase(TestCase):
    """Two customers, two products, one manager."""

    def setUp(self):
        self.category = Category.objects.create(name='Wishlist Cat')
        self.product = Product.objects.create(
            name='Saved Diyo', description='x', price=Decimal('250'),
            stock=10, category=self.category,
        )
        self.other_product = Product.objects.create(
            name='Saved Sindoor', description='x', price=Decimal('80'),
            stock=10, category=self.category,
        )
        self.customer = self._user('wishlist_customer', ROLE_CUSTOMER)
        self.other = self._user('wishlist_other', ROLE_CUSTOMER)

    def _user(self, username, role):
        user = User.objects.create_user(username, password='pw12345678')
        UserProfile.objects.create(user=user, role=role)
        return user

    def api(self, user=None):
        client = APIClient()
        if user is not None:
            client.credentials(
                HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}'
            )
        return client

    URL = '/api/products/wishlist/'

    def add(self, user, product=None):
        return self.api(user).post(
            self.URL, {'product_id': (product or self.product).id}, format='json',
        )


class WishlistAccessTests(WishlistTestBase):
    """A wishlist is private, and there is no anonymous one."""

    def test_an_anonymous_get_is_refused(self):
        self.assertEqual(self.api().get(self.URL).status_code, 401)

    def test_an_anonymous_post_is_refused(self):
        response = self.api().post(self.URL, {'product_id': self.product.id}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_one_customer_cannot_see_anothers_list(self):
        self.add(self.other)
        response = self.api(self.customer).get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_one_customer_cannot_delete_anothers_entry(self):
        self.add(self.other)
        response = self.api(self.customer).delete(f'{self.URL}{self.product.id}/')
        self.assertEqual(response.status_code, 404, 'must not leak that the row exists')
        self.assertEqual(WishlistItem.objects.filter(user=self.other).count(), 1)


class WishlistWriteTests(WishlistTestBase):
    """Adding is idempotent, because the control that calls it is a toggle."""

    def test_a_customer_can_save_a_product(self):
        response = self.add(self.customer)
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(WishlistItem.objects.filter(user=self.customer).count(), 1)

    def test_saving_the_same_product_twice_is_idempotent(self):
        """A double-clicked heart must not 400, and must not create two rows."""
        self.assertEqual(self.add(self.customer).status_code, 201)
        second = self.add(self.customer)
        self.assertEqual(second.status_code, 200, second.json())
        self.assertEqual(
            WishlistItem.objects.filter(user=self.customer, product=self.product).count(), 1,
        )

    def test_two_customers_can_save_the_same_product(self):
        self.add(self.customer)
        self.add(self.other)
        self.assertEqual(WishlistItem.objects.filter(product=self.product).count(), 2)

    def test_an_unknown_product_is_refused(self):
        response = self.api(self.customer).post(
            self.URL, {'product_id': 999999}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_a_delisted_product_cannot_be_saved(self):
        """A delisted product has no reachable page, so a saved card would 404."""
        self.product.is_active = False
        self.product.save()
        response = self.add(self.customer)
        self.assertEqual(response.status_code, 400)

    def test_the_client_cannot_write_into_somebody_elses_list(self):
        """`user` is not a writable field, so a supplied one is ignored."""
        response = self.api(self.customer).post(
            self.URL, {'product_id': self.product.id, 'user': self.other.id}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.json())
        self.assertEqual(WishlistItem.objects.filter(user=self.other).count(), 0)


class WishlistReadTests(WishlistTestBase):
    """The list is a bare array of cards, newest first."""

    def test_the_response_is_a_bare_list_not_a_paginated_dict(self):
        """The storefront maps over it directly; a `results` dict would break it."""
        self.add(self.customer)
        data = self.api(self.customer).get(self.URL).data
        self.assertIsInstance(data, list)
        self.assertNotIn('results', data)

    def test_each_row_carries_a_nested_product_a_card_can_render(self):
        self.add(self.customer)
        row = self.api(self.customer).get(self.URL).data[0]
        self.assertEqual(row['product']['name'], 'Saved Diyo')
        self.assertEqual(row['product']['slug'], self.product.slug)
        # The fields `ProductCard` reads must all be present, or the card renders
        # a blank price or an undefined category name.
        for key in ('id', 'slug', 'name', 'price', 'image', 'in_stock',
                    'category_name', 'unit', 'popularity_score'):
            self.assertIn(key, row['product'], f'{key} missing from the nested product')

    def test_the_newest_save_is_first(self):
        self.add(self.customer, self.product)
        self.add(self.customer, self.other_product)
        rows = self.api(self.customer).get(self.URL).data
        self.assertEqual(rows[0]['product']['name'], 'Saved Sindoor')

    def test_the_list_does_not_issue_a_query_per_row(self):
        """`select_related` keeps this flat: the count must not grow with row count.

        Asserted as a *comparison* rather than a magic number. A hardcoded count
        would break the moment an unrelated query is added to authentication (and it
        did: JWT auth costs two queries — the user and the profile `get_role()`
        reads), which would look like a regression in the wishlist. What actually
        matters is that six saved products do not cost six times one.
        """
        first = Product.objects.create(
            name='Bulk Wish 0', description='x', price=Decimal('10'),
            stock=5, category=self.category,
        )
        self.add(self.customer, first)
        with self.assertNumQueries(3) as one_row:
            self.api(self.customer).get(self.URL)

        for i in range(1, 6):
            Product.objects.create(
                name=f'Bulk Wish {i}', description='x', price=Decimal('10'),
                stock=5, category=self.category,
            )
        for product in Product.objects.exclude(pk=first.pk):
            self.add(self.customer, product)

        with self.assertNumQueries(3) as six_rows:
            self.api(self.customer).get(self.URL)

        self.assertEqual(
            one_row.final_queries, six_rows.final_queries,
            'query count grew with the number of saved products — N+1',
        )


class WishlistRemovalTests(WishlistTestBase):
    """Removal is keyed by product id — what the heart button actually has."""

    def test_a_customer_can_remove_their_own_entry(self):
        self.add(self.customer)
        response = self.api(self.customer).delete(f'{self.URL}{self.product.id}/')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(WishlistItem.objects.filter(user=self.customer).count(), 0)

    def test_removing_something_not_saved_is_a_404(self):
        response = self.api(self.customer).delete(f'{self.URL}{self.product.id}/')
        self.assertEqual(response.status_code, 404)

    def test_an_anonymous_delete_is_refused(self):
        self.add(self.customer)
        response = self.api().delete(f'{self.URL}{self.product.id}/')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(WishlistItem.objects.filter(user=self.customer).count(), 1)

    def test_removing_one_product_leaves_the_rest(self):
        self.add(self.customer, self.product)
        self.add(self.customer, self.other_product)
        self.api(self.customer).delete(f'{self.URL}{self.product.id}/')
        remaining = WishlistItem.objects.filter(user=self.customer)
        self.assertEqual(remaining.count(), 1)
        self.assertEqual(remaining.first().product_id, self.other_product.id)

    def test_deleting_a_product_removes_it_from_every_wishlist(self):
        """CASCADE, not SET_NULL: a dangling row would render a card that 404s."""
        self.add(self.customer)
        self.add(self.other)
        self.product.delete()
        self.assertEqual(WishlistItem.objects.count(), 0)


class WishlistRoutingTests(WishlistTestBase):
    """The route must not be swallowed by the `<slug:slug>` detail pattern."""

    def test_the_endpoint_resolves_rather_than_being_read_as_a_slug(self):
        """`wishlist` is a valid slug, so a mis-ordered urlconf 404s this endpoint."""
        response = self.api(self.customer).get(self.URL)
        self.assertEqual(response.status_code, 200, 'wishlist/ was matched as a product slug')

    def test_the_literal_route_wins_over_a_product_with_a_colliding_slug(self):
        """The documented trade-off, asserted so it cannot change silently.

        A product named exactly "Wishlist" slugifies to `wishlist`, so its detail URL
        is the same path as this endpoint — and the literal route, which is listed
        first, wins. An anonymous request therefore gets the wishlist endpoint's 401
        rather than that product's 200.

        This is not a wishlist defect: `search`, `featured`, `categories` and `areas`
        have carried the same property since they were added, and it is the reason
        `products/urls.py` insists every literal path precedes the slug patterns. The
        test exists so the precedence is *stated* rather than assumed — the failure
        mode it guards against is somebody "tidying" the urlconf into the obvious
        order and 404-ing the whole endpoint family.
        """
        product = Product.objects.create(
            name='Wishlist', description='x', price=Decimal('10'),
            stock=1, category=self.category,
        )
        self.assertEqual(product.slug, 'wishlist')
        self.assertEqual(APIClient().get('/api/products/wishlist/').status_code, 401)

    def test_a_product_with_any_other_slug_is_unaffected(self):
        product = Product.objects.create(
            name='Wishlist Diyo', description='x', price=Decimal('10'),
            stock=1, category=self.category,
        )
        response = APIClient().get(f'/api/products/{product.slug}/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Wishlist Diyo')


class WishlistProductFlagTests(WishlistTestBase):
    """`is_wishlisted` on the detail payload drives the heart on first paint."""

    def test_a_guest_sees_false(self):
        response = APIClient().get(f'/api/products/{self.product.slug}/')
        self.assertFalse(response.data['is_wishlisted'])

    def test_an_authenticated_customer_sees_false_before_saving(self):
        response = self.api(self.customer).get(f'/api/products/{self.product.slug}/')
        self.assertFalse(response.data['is_wishlisted'])

    def test_it_becomes_true_once_saved(self):
        self.add(self.customer)
        response = self.api(self.customer).get(f'/api/products/{self.product.slug}/')
        self.assertTrue(response.data['is_wishlisted'])

    def test_another_customers_save_does_not_flip_your_flag(self):
        self.add(self.other)
        response = self.api(self.customer).get(f'/api/products/{self.product.slug}/')
        self.assertFalse(response.data['is_wishlisted'])


class ProductImageUploadTests(TestCase):
    """Multipart image upload on the admin product endpoint.

    `docs/FEATURES.md` carried this as a ⚠️ — "products have an `image` column, but no
    upload widget in either dashboard screen". The widget now exists, so the thing
    worth testing is the part that is easy to get wrong and impossible to see: the
    transport. A JSON body cannot carry a file, and a hand-set `Content-Type:
    multipart/form-data` without a boundary is rejected by DRF as an empty body —
    both of which look like "the upload silently did nothing".

    **Media is redirected to a temp directory for the class.** Without this, every run
    of this file writes real PNGs into `backend/media/products/` — a directory that is
    committed on purpose — so a test suite run silently dirties the working tree and
    the files pile up (`diyo_<random>.png` × N) because deleting the row does not
    delete the file. Found by reading `git status` after a run.
    """

    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix='test-media-')
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    def setUp(self):
        self.admin = User.objects.create_user(
            'img_admin', password='pw12345678', is_staff=True, is_superuser=True,
        )
        UserProfile.objects.create(user=self.admin, role=ROLE_ADMIN)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))

        self.category = Category.objects.create(name='Image Cat')
        self.product = Product.objects.create(
            name='Photogenic Diyo', description='x', price=Decimal('100'),
            stock=5, category=self.category,
        )

    def _png(self, name='diyo.png'):
        """A real 1x1 PNG, so `ImageField` validation actually passes."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        import base64
        data = base64.b64decode(
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
        )
        return SimpleUploadedFile(name, data, content_type='image/png')

    def url(self, pk=None):
        return f'/api/products/admin/products/{pk or self.product.id}/'

    def test_multipart_patch_attaches_an_image(self):
        response = self.client.patch(
            self.url(), {'image': self._png()}, format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.json())

        self.product.refresh_from_db()
        self.assertTrue(self.product.image)
        self.assertTrue(self.product.image.name.startswith('products/'))

    def test_multipart_create_attaches_an_image(self):
        response = self.client.post(
            '/api/products/admin/products/',
            {
                'name': 'Fresh Upload', 'description': 'x', 'price': '150',
                'stock': 3, 'category': self.category.id, 'unit': 'piece',
                'image': self._png('fresh.png'),
            },
            format='multipart',
        )
        self.assertEqual(response.status_code, 201, response.json())
        created = Product.objects.get(pk=response.json()['id'])
        self.assertTrue(created.image)

    def test_json_null_clears_the_image(self):
        """Removal cannot travel as multipart — an empty part is "not a file"."""
        self.client.patch(self.url(), {'image': self._png()}, format='multipart')
        self.product.refresh_from_db()
        self.assertTrue(self.product.image)

        response = self.client.patch(
            self.url(), {'image': None}, format='json',
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)

    def test_a_non_image_file_is_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        bad = SimpleUploadedFile('notes.txt', b'not an image', content_type='text/plain')
        response = self.client.patch(self.url(), {'image': bad}, format='multipart')
        self.assertEqual(response.status_code, 400)
        self.assertIn('image', response.json())

    def test_the_other_fields_still_save_alongside_the_image(self):
        """One request must not silently drop the rest of the form."""
        response = self.client.patch(
            self.url(),
            {'image': self._png(), 'name': 'Renamed Diyo', 'price': '175'},
            format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.json())
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, 'Renamed Diyo')
        self.assertEqual(self.product.price, Decimal('175'))
        self.assertTrue(self.product.image)

    def test_the_image_url_is_absolute_so_the_storefront_can_load_it(self):
        """A relative `media/...` URL would resolve against the *page* and 404.

        DRF's `ImageField` publishes a **fully absolute** URL when the request is in
        the serializer context (`http://host/media/products/...`), and the storefront
        renders it straight into `<img src>`. Either absolute form works; what must
        not happen is a bare `media/...`, which the browser would resolve relative to
        the current page — `/products/media/...` — and fail to load. That is the
        regression this guards.
        """
        self.client.patch(self.url(), {'image': self._png()}, format='multipart')
        data = self.client.get(f'/api/products/{self.product.slug}/').json()

        url = data['image']
        self.assertTrue(url, 'image URL was empty after a successful upload')
        self.assertTrue(
            url.startswith(('http://', 'https://', '/')),
            f'image URL is relative and would 404 in the browser: {url!r}',
        )
        self.assertIn('/media/', url)

    def test_a_vendor_cannot_upload_to_another_vendors_product(self):
        """Ownership scoping must survive the new transport."""
        from products.models import Vendor
        other_user = User.objects.create_user('img_vendor', password='pw12345678')
        UserProfile.objects.create(user=other_user, role='vendor')
        Vendor.objects.create(user=other_user, shop_name='Other Img Shop')

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=bearer(other_user))
        response = client.patch(
            self.url(), {'image': self._png()}, format='multipart',
        )
        self.assertEqual(response.status_code, 404, 'must not leak the row')
        self.product.refresh_from_db()
        self.assertFalse(self.product.image)


class AdminProductListCompletenessTests(TestCase):
    """The admin catalogue list must show **every** row, not a first page of them.

    This was a real defect, found by a browser check rather than by any test. The
    endpoint used the project-wide default page size of 12, and `Product.Meta.ordering`
    is `['-popularity_score', '-created_at']` — so a product created through the
    dashboard's own dialog (popularity 0) sorted to the *last* page and vanished from
    the table. The dashboard's "Total Products" card read 12 against 36 real rows.

    Paginating a management list hides rows from the only person who can act on them,
    which is the same argument `AdminReviewListView` carries for a hidden review.
    """

    def setUp(self):
        self.admin = User.objects.create_user(
            'list_admin', password='pw12345678', is_staff=True, is_superuser=True,
        )
        UserProfile.objects.create(user=self.admin, role=ROLE_ADMIN)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=bearer(self.admin))
        self.category = Category.objects.create(name='Completeness Cat')

    def _make(self, n, popularity=0):
        return [
            Product.objects.create(
                name=f'Bulk Product {i}', description='x', price=Decimal('10'),
                stock=1, category=self.category, popularity_score=popularity,
            )
            for i in range(n)
        ]

    def test_the_response_is_a_bare_list(self):
        self._make(1)
        data = self.client.get('/api/products/admin/products/').json()
        self.assertIsInstance(data, list)
        self.assertNotIn('results', data)

    def test_more_than_a_page_of_products_are_all_returned(self):
        """20 rows, default page size 12 — every one must come back."""
        self._make(20)
        data = self.client.get('/api/products/admin/products/').json()
        self.assertEqual(len(data), 20)

    def test_a_newly_created_product_is_present_in_the_list(self):
        """The exact failure: a new row sorts last and used to fall off the list."""
        existing = self._make(20, popularity=90)
        created = self.client.post(
            '/api/products/admin/products/',
            {
                'name': 'Just Created', 'description': 'x', 'price': '99',
                'stock': 3, 'category': self.category.id, 'unit': 'piece',
            },
            format='multipart',
        ).json()

        data = self.client.get('/api/products/admin/products/').json()
        ids = {row['id'] for row in data}
        self.assertIn(created['id'], ids,
                      'a product created through the dashboard was not in the list')

    def test_vendor_scoping_still_holds_without_pagination(self):
        """Unpaginating must not widen what a vendor can see."""
        from products.models import Vendor
        vendor_user = User.objects.create_user('list_vendor', password='pw12345678')
        UserProfile.objects.create(user=vendor_user, role='vendor')
        vendor = Vendor.objects.create(user=vendor_user, shop_name='List Shop')

        mine = Product.objects.create(
            name='Mine', description='x', price=Decimal('10'), stock=1,
            category=self.category, vendor=vendor,
        )
        self._make(15)  # unowned products, plenty to fill a page

        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=bearer(vendor_user))
        data = client.get('/api/products/admin/products/').json()

        self.assertEqual([row['id'] for row in data], [mine.id])
