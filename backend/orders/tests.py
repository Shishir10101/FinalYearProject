"""Tests for real order status history.

Before ``OrderStatusEvent`` existed, the customer's order tracker was derived from
the single mutable ``Order.status`` column. It could say *where* an order was but
never *when* it got there, because nothing stored the transitions — "Shipped" was
permanently undated and the tracker could not answer the one question a customer
actually asks.

A test that only asserted "the timeline has five steps" would pass against that
broken implementation. The tests below assert on **timestamps and transitions**,
which the old code could not produce at all.

Run with::

    python manage.py test orders -v 2
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import UserProfile
from core.permissions import ROLE_ADMIN, ROLE_CUSTOMER
from products.models import Area, Category, Product
from .models import Cart, Order, OrderItem, OrderStatusEvent


def bearer(user):
    """The API is JWT-only — ``force_login`` silently yields 401 here."""
    return f'Bearer {RefreshToken.for_user(user).access_token}'


class StatusHistoryTestBase(TestCase):
    def setUp(self):
        self.area = Area.objects.get(slug='kathmandu')
        self.category = Category.objects.create(name='Order History Cat')

        self.customer = User.objects.create_user('buyer', password='pw12345678')
        UserProfile.objects.create(user=self.customer, role=ROLE_CUSTOMER)

        self.admin = User.objects.create_user(
            'ops', password='pw12345678', is_staff=True, is_superuser=True,
        )
        UserProfile.objects.create(user=self.admin, role=ROLE_ADMIN)

        self.product = Product.objects.create(
            name='History Test Dhoop', description='x', price=Decimal('100'),
            stock=100, category=self.category, popularity_score=5,
        )

        self.order = Order.objects.create(
            user=self.customer,
            total_amount=Decimal('200'),
            delivery_fee=Decimal('100'),
            shipping_address='Test Tole, Kathmandu',
            shipping_city='kathmandu',
            phone='9800000000',
        )

    def api(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=bearer(user))
        return client


class EventRecordingTests(StatusHistoryTestBase):
    """The model-level contract of ``OrderStatusEvent.record``."""

    def test_record_appends_a_row_with_from_and_to(self):
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending')
        event = self.order.status_events.get()
        self.assertEqual(event.from_status, 'pending')
        self.assertEqual(event.to_status, 'confirmed')

    def test_explicit_timestamp_is_preserved(self):
        """Guards the ``auto_now_add`` trap.

        ``auto_now_add=True`` silently discards any value passed to the
        constructor, which would have made the backfill migration stamp every
        historical order with "now" instead of its real ``created_at``. The field
        deliberately uses ``default=timezone.now`` so an explicit value sticks.
        """
        past = timezone.now() - timedelta(days=30)
        event = OrderStatusEvent.record(self.order, 'shipped', at=past)
        event.refresh_from_db()
        self.assertAlmostEqual(
            event.created_at, past, delta=timedelta(seconds=1),
            msg='explicit timestamp was overwritten — is created_at auto_now_add?',
        )

    def test_from_status_defaults_to_the_stored_status(self):
        OrderStatusEvent.record(self.order, 'confirmed')
        self.assertEqual(self.order.status_events.get().from_status, 'pending')

    def test_events_come_back_oldest_first(self):
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending')
        OrderStatusEvent.record(self.order, 'processing', from_status='confirmed')
        OrderStatusEvent.record(self.order, 'shipped', from_status='processing')
        to_statuses = list(self.order.status_events.values_list('to_status', flat=True))
        self.assertEqual(to_statuses, ['confirmed', 'processing', 'shipped'])

    def test_changed_by_is_recorded_for_staff_actions(self):
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending',
                                changed_by=self.admin)
        self.assertEqual(self.order.status_events.get().changed_by, self.admin)

    def test_deleting_the_user_keeps_the_event(self):
        """History must outlive the staff account that wrote it."""
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending',
                                changed_by=self.admin)
        self.admin.delete()
        self.assertEqual(self.order.status_events.count(), 1)
        self.assertIsNone(self.order.status_events.get().changed_by)


class CheckoutHistoryTests(StatusHistoryTestBase):
    """Checkout must open the history, not leave the order undated."""

    def _checkout(self, payment_method='cod'):
        Cart.objects.create(user=self.customer, product=self.product, quantity=1)
        return self.api(self.customer).post('/api/orders/checkout/', {
            'shipping_address': 'Test Tole, Kathmandu',
            'shipping_city': 'kathmandu',
            'phone': '9800000000',
            'payment_method': payment_method,
        }, format='json')

    def test_cod_checkout_records_a_pending_event(self):
        response = self._checkout('cod')
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(id=response.json()['id'])
        events = list(order.status_events.all())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].to_status, 'pending')
        self.assertEqual(events[0].from_status, '')
        self.assertEqual(order.status, 'pending')

    def test_mocked_wallet_checkout_records_both_transitions(self):
        """The mock marks the order confirmed — that jump must be in the history."""
        response = self._checkout('esewa')
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(id=response.json()['id'])
        self.assertEqual(order.status, 'confirmed')
        transitions = list(order.status_events.values_list('from_status', 'to_status'))
        self.assertEqual(transitions, [('', 'pending'), ('pending', 'confirmed')])

    def test_timeline_dates_the_placed_step(self):
        response = self._checkout('cod')
        timeline = response.json()['timeline']
        placed = timeline['steps'][0]
        self.assertEqual(placed['key'], 'pending')
        self.assertIsNotNone(placed['at'], 'the placed step must carry a timestamp')

    def test_undated_future_steps_are_null_not_invented(self):
        """A step that has not happened must not borrow a timestamp."""
        response = self._checkout('cod')
        steps = {s['key']: s for s in response.json()['timeline']['steps']}
        self.assertIsNone(steps['shipped']['at'])
        self.assertIsNone(steps['delivered']['at'])


class AdminStatusUpdateTests(StatusHistoryTestBase):
    """Every real status change must be recorded, and only real ones."""

    def test_status_change_appends_an_event_with_actor(self):
        response = self.api(self.admin).patch(
            f'/api/orders/admin/orders/{self.order.id}/',
            {'status': 'confirmed'}, format='json',
        )
        self.assertEqual(response.status_code, 200)
        event = self.order.status_events.get()
        self.assertEqual((event.from_status, event.to_status), ('pending', 'confirmed'))
        self.assertEqual(event.changed_by, self.admin)

    def test_resaving_the_same_status_does_not_duplicate_history(self):
        client = self.api(self.admin)
        url = f'/api/orders/admin/orders/{self.order.id}/'
        client.patch(url, {'status': 'confirmed'}, format='json')
        client.patch(url, {'status': 'confirmed'}, format='json')
        client.patch(url, {'status': 'confirmed'}, format='json')
        self.assertEqual(self.order.status_events.count(), 1,
                         'repeated saves of the same status must not pile up events')

    def test_payment_status_change_alone_does_not_create_a_status_event(self):
        self.api(self.admin).patch(
            f'/api/orders/admin/orders/{self.order.id}/',
            {'payment_status': 'paid'}, format='json',
        )
        self.assertEqual(self.order.status_events.count(), 0)

    def test_full_ladder_records_five_events_in_order(self):
        client = self.api(self.admin)
        url = f'/api/orders/admin/orders/{self.order.id}/'
        for status_value in ['confirmed', 'processing', 'shipped', 'delivered']:
            self.assertEqual(
                client.patch(url, {'status': status_value}, format='json').status_code, 200,
            )
        self.assertEqual(
            list(self.order.status_events.values_list('to_status', flat=True)),
            ['confirmed', 'processing', 'shipped', 'delivered'],
        )

    def test_customer_cannot_change_status(self):
        response = self.api(self.customer).patch(
            f'/api/orders/admin/orders/{self.order.id}/',
            {'status': 'delivered'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.order.status_events.count(), 0)


class TimelineTimestampTests(StatusHistoryTestBase):
    """The timeline must report real times, and admit when it has none."""

    def _detail(self):
        return self.api(self.customer).get(f'/api/orders/{self.order.id}/').json()

    def test_step_without_an_event_reports_null_rather_than_created_at(self):
        """An order with no recorded history must not fake a delivery date.

        This is the shape of every order placed before status tracking existed:
        one backfilled event. Steps with no event return ``at: null`` and the UI
        renders "not recorded".
        """
        OrderStatusEvent.record(self.order, 'pending', from_status='')
        steps = {s['key']: s for s in self._detail()['timeline']['steps']}
        self.assertIsNotNone(steps['pending']['at'])
        for key in ['confirmed', 'processing', 'shipped', 'delivered']:
            self.assertIsNone(steps[key]['at'], f'{key} must not have an invented timestamp')

    def test_placed_step_falls_back_to_created_at_when_unrecorded(self):
        """An order *was* necessarily placed at ``created_at`` — that is a fact."""
        timeline = self._detail()['timeline']
        self.assertEqual(timeline['steps'][0]['key'], 'pending')
        self.assertIsNotNone(timeline['steps'][0]['at'])

    def test_each_completed_step_carries_its_own_distinct_time(self):
        base = timezone.now() - timedelta(days=4)
        OrderStatusEvent.record(self.order, 'pending', from_status='', at=base)
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending',
                                at=base + timedelta(days=1))
        OrderStatusEvent.record(self.order, 'processing', from_status='confirmed',
                                at=base + timedelta(days=2))
        self.order.status = 'processing'
        self.order.save()

        steps = {s['key']: s for s in self._detail()['timeline']['steps']}
        self.assertNotEqual(steps['pending']['at'], steps['confirmed']['at'])
        self.assertLess(steps['pending']['at'], steps['confirmed']['at'])
        self.assertLess(steps['confirmed']['at'], steps['processing']['at'])
        self.assertIsNone(steps['shipped']['at'])

    def test_history_block_lists_what_actually_happened(self):
        OrderStatusEvent.record(self.order, 'pending', from_status='')
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending')
        history = self._detail()['timeline']['history']
        self.assertEqual([h['status'] for h in history], ['pending', 'confirmed'])
        self.assertTrue(all(h['at'] for h in history))

    def test_history_does_not_leak_internal_notes_or_staff_identity(self):
        """The customer timeline is not a staff audit log."""
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending',
                                changed_by=self.admin, note='internal ops note')
        timeline = self._detail()['timeline']
        for entry in timeline['history']:
            self.assertNotIn('note', entry)
            self.assertNotIn('changed_by', entry)
        self.assertNotIn('internal ops note', str(timeline))

    def test_cancelled_timeline_dates_the_cancellation(self):
        self.order.status = 'cancelled'
        self.order.save()
        OrderStatusEvent.record(self.order, 'cancelled', from_status='pending')
        timeline = self._detail()['timeline']
        self.assertTrue(timeline['is_terminal'])
        self.assertEqual(timeline['current'], 'cancelled')
        cancelled_step = [s for s in timeline['steps'] if s['key'] == 'cancelled'][0]
        self.assertIsNotNone(cancelled_step['at'])

    def test_delivered_order_is_terminal_and_dated(self):
        self.order.status = 'delivered'
        self.order.save()
        OrderStatusEvent.record(self.order, 'delivered', from_status='shipped')
        timeline = self._detail()['timeline']
        self.assertTrue(timeline['is_terminal'])
        delivered = [s for s in timeline['steps'] if s['key'] == 'delivered'][0]
        self.assertEqual(delivered['state'], 'done')
        self.assertIsNotNone(delivered['at'])

    def test_timeline_is_stable_across_repeated_requests(self):
        OrderStatusEvent.record(self.order, 'pending', from_status='')
        OrderStatusEvent.record(self.order, 'confirmed', from_status='pending')
        first = self._detail()['timeline']
        second = self._detail()['timeline']
        self.assertEqual([s['key'] for s in first['steps']],
                         [s['key'] for s in second['steps']])
        self.assertEqual([h['status'] for h in first['history']],
                         [h['status'] for h in second['history']])


class AddPujaToCartTests(StatusHistoryTestBase):
    """POST /api/orders/cart/add-puja/<id>/ — shop by ritual.

    The Puja entry point exists so a shopper can buy what a ceremony needs
    *without* a ready-made kit, which is why this is driven by the ritual's own
    item list rather than by a kit's.
    """

    def setUp(self):
        super().setUp()
        from festivals.models import Puja, PujaItem

        self.puja = Puja.objects.create(name='Cart Test Ritual', slug='cart-test-ritual')
        self.required = self.product
        self.optional = Product.objects.create(
            name='Optional Extra', description='x', price=Decimal('60'),
            stock=20, category=self.category,
        )
        PujaItem.objects.create(puja=self.puja, product=self.required, quantity=3, is_required=True)
        PujaItem.objects.create(puja=self.puja, product=self.optional, quantity=1, is_required=False)

    def add(self, puja_id=None):
        return self.api(self.customer).post(
            f'/api/orders/cart/add-puja/{puja_id if puja_id is not None else self.puja.id}/',
            {}, format='json',
        )

    def test_adds_the_required_items(self):
        response = self.add()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['added'], 1)
        self.assertEqual(Cart.objects.get(user=self.customer).quantity, 3)

    def test_does_not_add_optional_items(self):
        """Silently filling the cart with extras would be putting words in the
        customer's mouth — the ritual's required list is what gets added."""
        self.add()
        self.assertFalse(Cart.objects.filter(user=self.customer, product=self.optional).exists())

    def test_out_of_stock_items_are_skipped_and_reported(self):
        self.required.stock = 0
        self.required.save()
        body = self.add().json()
        self.assertEqual(body['added'], 0)
        self.assertIn('skipped', body)
        self.assertIn(self.required.name, body['skipped'][0])
        self.assertFalse(Cart.objects.filter(user=self.customer).exists())

    def test_stock_smaller_than_required_quantity_is_skipped(self):
        self.required.stock = 2  # ritual wants 3
        self.required.save()
        self.assertEqual(self.add().json()['added'], 0)

    def test_inactive_products_are_skipped(self):
        self.required.is_active = False
        self.required.save()
        self.assertEqual(self.add().json()['added'], 0)

    def test_merges_into_an_existing_cart_line(self):
        Cart.objects.create(user=self.customer, product=self.required, quantity=2)
        self.add()
        self.assertEqual(Cart.objects.get(user=self.customer).quantity, 5)

    def test_unknown_ritual_is_404(self):
        self.assertEqual(self.add(puja_id=999999).status_code, 404)

    def test_inactive_ritual_is_404(self):
        self.puja.is_active = False
        self.puja.save()
        self.assertEqual(self.add().status_code, 404)

    def test_requires_authentication(self):
        client = APIClient()
        response = client.post(f'/api/orders/cart/add-puja/{self.puja.id}/', {}, format='json')
        self.assertEqual(response.status_code, 401)

    def test_cannot_put_another_users_cart_at_risk(self):
        """The cart is always keyed on request.user, never on anything supplied."""
        other = User.objects.create_user('other_buyer', password='pw12345678')
        UserProfile.objects.create(user=other, role=ROLE_CUSTOMER)
        self.add()
        self.assertFalse(Cart.objects.filter(user=other).exists())
