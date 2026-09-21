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
from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER
from orders.models import Order, OrderItem
from .models import Area, Category, Product, Review


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
