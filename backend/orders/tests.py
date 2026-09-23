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


class CancellationStockTests(StatusHistoryTestBase):
    """Cancelling an order must return its units to inventory.

    This was a real, silent leak. `CheckoutView` decrements `product.stock` for every
    line, and **nothing ever released it** — `AdminOrderUpdateView` only wrote a history
    row. So every cancellation shrank the catalogue permanently: the goods were back on
    the shelf but the system still counted them as gone, which then produced false
    low-stock and restock alerts. Measured on this project's own data, the leak had
    reached **538 units across 23 products** before it was found.

    It was invisible to the whole suite because no test ever cancelled an order and then
    looked at stock.
    """

    def _order_with(self, quantity=2):
        OrderItem.objects.create(
            order=self.order, product=self.product,
            product_name=self.product.name, quantity=quantity,
            price=self.product.price,
        )
        # Simulate the reservation checkout performs.
        self.product.stock -= quantity
        self.product.save(update_fields=['stock'])
        return self.product.stock

    def _set_status(self, new_status):
        return self.api(self.admin).patch(
            f'/api/orders/admin/orders/{self.order.id}/',
            {'status': new_status}, format='json',
        )

    def test_cancelling_returns_the_units(self):
        stock_after_checkout = self._order_with(quantity=3)
        self.assertEqual(stock_after_checkout, 97)

        response = self._set_status('cancelled')
        self.assertEqual(response.status_code, 200, response.json())

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100,
                         'the cancelled units were not returned to stock')

    def test_cancelling_twice_does_not_restore_twice(self):
        """Idempotency matters more than the happy path: a double restore inflates
        inventory exactly as much as the original leak deflated it."""
        self._order_with(quantity=3)
        self._set_status('cancelled')
        self._set_status('cancelled')

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)

    def test_a_status_change_that_is_not_a_cancellation_leaves_stock_alone(self):
        self._order_with(quantity=2)
        for status in ('confirmed', 'processing', 'shipped', 'delivered'):
            self._set_status(status)
            self.product.refresh_from_db()
            self.assertEqual(self.product.stock, 98,
                             f'{status} should not have moved stock')

    def test_reinstating_a_cancelled_order_takes_the_units_back(self):
        self._order_with(quantity=2)
        self._set_status('cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)

        self._set_status('confirmed')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 98,
                         'reinstating did not re-reserve the stock')

    def test_reinstating_is_refused_when_the_stock_is_gone(self):
        """Refusing beats promising a customer something the shop cannot ship."""
        self._order_with(quantity=2)
        self._set_status('cancelled')

        # Someone else buys the last of it.
        self.product.stock = 1
        self.product.save(update_fields=['stock'])

        response = self._set_status('confirmed')
        self.assertEqual(response.status_code, 400, response.json())
        self.assertIn('status', response.json())

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 1, 'a refused reinstate changed stock anyway')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'cancelled',
                         'the status moved even though the request was refused')

    def test_a_refused_reinstate_does_not_partially_reserve_other_lines(self):
        """The atomic block must roll back lines already decremented."""
        other = Product.objects.create(
            name='Second Line Sindoor', description='x', price=Decimal('50'),
            stock=50, category=self.category,
        )
        # Two lines: one restorable, one not. If the restorable one is decremented
        # before the other fails, stock is silently wrong.
        OrderItem.objects.create(order=self.order, product=self.product,
                                 product_name=self.product.name, quantity=2,
                                 price=self.product.price)
        OrderItem.objects.create(order=self.order, product=other,
                                 product_name=other.name, quantity=5,
                                 price=other.price)
        self.product.stock -= 2
        self.product.save(update_fields=['stock'])
        other.stock -= 5
        other.save(update_fields=['stock'])

        self._set_status('cancelled')
        self.product.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual((self.product.stock, other.stock), (100, 50))

        other.stock = 1
        other.save(update_fields=['stock'])

        response = self._set_status('confirmed')
        self.assertEqual(response.status_code, 400, response.json())

        self.product.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(self.product.stock, 100,
                         'the first line was decremented before the second line failed')
        self.assertEqual(other.stock, 1)

    def test_a_line_whose_product_was_deleted_does_not_break_cancellation(self):
        """`OrderItem.product` is `SET_NULL`; a deleted product must not 500 the cancel."""
        OrderItem.objects.create(
            order=self.order, product=None, product_name='Deleted Thing',
            quantity=4, price=Decimal('10'),
        )
        self._order_with(quantity=2)

        response = self._set_status('cancelled')
        self.assertEqual(response.status_code, 200, response.json())
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)

    def test_the_history_row_says_what_happened_to_stock(self):
        self._order_with(quantity=3)
        self._set_status('cancelled')

        event = self.order.status_events.order_by('-id').first()
        self.assertEqual(event.to_status, 'cancelled')
        self.assertIn('3 unit', event.note,
                      f'note does not explain the stock movement: {event.note!r}')

    def test_a_customer_cannot_move_a_status(self):
        """The stock movement must not open a route for a customer to mint inventory."""
        self._order_with(quantity=2)
        response = self.api(self.customer).patch(
            f'/api/orders/admin/orders/{self.order.id}/',
            {'status': 'cancelled'}, format='json',
        )
        self.assertEqual(response.status_code, 403)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 98, 'a customer moved stock')

    def test_popularity_score_is_deliberately_not_reversed(self):
        """`popularity_score` records demand, not settlement — it stays monotonic.

        Documented as a decision rather than an oversight: the two fields are not
        symmetric. `stock` is a factual count of what is on the shelf and must be
        exact; `popularity_score` is a signal that a product was asked for.
        """
        self._order_with(quantity=2)
        self.product.popularity_score += 2
        self.product.save(update_fields=['popularity_score'])

        self._set_status('cancelled')
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)
        self.assertEqual(self.product.popularity_score, 7)


class PurgeRestockTests(StatusHistoryTestBase):
    """`purge_verification_orders` must release the stock its orders reserved."""

    def _scratch_order(self, quantity=2, status='pending'):
        order = Order.objects.create(
            user=self.customer, total_amount=Decimal('300'),
            delivery_fee=Decimal('100'), shipping_address='Scratch',
            shipping_city='kathmandu', phone='9800000000',
            notes='Placed by verify_day13.py — safe to delete', status=status,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=quantity, price=self.product.price,
        )
        self.product.stock -= quantity
        self.product.save(update_fields=['stock'])
        return order

    def test_purging_returns_the_reserved_stock(self):
        from django.core.management import call_command
        from io import StringIO

        self._scratch_order(quantity=4)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 96)

        call_command('purge_verification_orders', stdout=StringIO())

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100,
                         'purging deleted the order without returning its stock')
        self.assertFalse(Order.objects.filter(notes__icontains='verify_day13.py').exists())

    def test_purging_a_cancelled_order_does_not_double_restock(self):
        """Cancelling already released the units; deleting must not release them again."""
        from django.core.management import call_command
        from io import StringIO

        order = self._scratch_order(quantity=4)
        self.api(self.admin).patch(
            f'/api/orders/admin/orders/{order.id}/', {'status': 'cancelled'}, format='json',
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)

        call_command('purge_verification_orders', stdout=StringIO())

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100, 'the units were returned twice')

    def test_no_restock_flag_leaves_stock_alone(self):
        from django.core.management import call_command
        from io import StringIO

        self._scratch_order(quantity=4)
        call_command('purge_verification_orders', '--no-restock', stdout=StringIO())

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 96)

    def test_seeded_orders_are_never_touched(self):
        """A real order has no verifier marker, so the sweep must skip it."""
        from django.core.management import call_command
        from io import StringIO

        real = Order.objects.create(
            user=self.customer, total_amount=Decimal('200'),
            delivery_fee=Decimal('100'), shipping_address='A real address',
            shipping_city='kathmandu', phone='9800000000', notes='',
        )
        OrderItem.objects.create(
            order=real, product=self.product, product_name=self.product.name,
            quantity=1, price=self.product.price,
        )

        call_command('purge_verification_orders', stdout=StringIO())
        self.assertTrue(Order.objects.filter(pk=real.pk).exists(),
                        'a non-verifier order was deleted')


class PurgePopularityTests(StatusHistoryTestBase):
    """`purge_verification_orders` must also undo the demand signal it created.

    `popularity_score` is only ever incremented, by `CheckoutView`, and cancellation
    deliberately does not reverse it — a cancelled order still means a customer asked for
    something. A *verification* order means nobody did, yet the field feeds the
    recommendation engine's popularity bonus, the trending list, the default catalogue
    ordering and the search tie-break. Left in place, fixture traffic made the demo
    recommend whatever the test suite happened to buy: measured at **591 points across
    23 products**, with one product at 256 against a seeded 98.
    """

    def _scratch_order(self, quantity=3, status='pending', notes=None):
        order = Order.objects.create(
            user=self.customer, total_amount=Decimal('300'),
            delivery_fee=Decimal('100'), shipping_address='Scratch',
            shipping_city='kathmandu', phone='9800000000',
            notes=notes or 'Placed by verify_day13.py — safe to delete',
            status=status,
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=quantity, price=self.product.price,
        )
        # What checkout does to both fields.
        self.product.stock -= quantity
        self.product.popularity_score += quantity
        self.product.save(update_fields=['stock', 'popularity_score'])
        return order

    def _purge(self, *args):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('purge_verification_orders', *args, stdout=out)
        return out.getvalue()

    def test_purging_reverses_the_popularity_it_added(self):
        self._scratch_order(quantity=3)
        self.product.refresh_from_db()
        self.assertEqual(self.product.popularity_score, 8)

        self._purge()

        self.product.refresh_from_db()
        self.assertEqual(self.product.popularity_score, 5,
                         'the fixture demand signal was left in place')

    def test_a_cancelled_fixture_order_still_has_its_popularity_reversed(self):
        """Stock is not re-released for a cancelled order, but popularity must be.

        Two fields, two rules, and the difference is deliberate: cancellation returns the
        stock but keeps the demand signal, so the purge has to undo the signal itself.
        """
        order = self._scratch_order(quantity=4)
        self.api(self.admin).patch(
            f'/api/orders/admin/orders/{order.id}/', {'status': 'cancelled'}, format='json',
        )
        self.product.refresh_from_db()
        # Cancelling returned the stock but left popularity alone.
        self.assertEqual(self.product.stock, 100)
        self.assertEqual(self.product.popularity_score, 9)

        self._purge()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100, 'stock was returned twice')
        self.assertEqual(self.product.popularity_score, 5,
                         'a cancelled fixture order kept its demand signal')

    def test_reversal_is_floored_at_zero(self):
        """`popularity_score` is a PositiveIntegerField — an unguarded subtraction raises."""
        self._scratch_order(quantity=3)
        self.product.popularity_score = 1
        self.product.save(update_fields=['popularity_score'])

        self._purge()

        self.product.refresh_from_db()
        self.assertEqual(self.product.popularity_score, 0)

    def test_no_restock_leaves_popularity_alone_too(self):
        self._scratch_order(quantity=3)
        self._purge('--no-restock')

        self.product.refresh_from_db()
        self.assertEqual(self.product.popularity_score, 8)

    def test_a_real_order_is_untouched(self):
        """No verifier marker, so neither stock nor popularity may move."""
        real = Order.objects.create(
            user=self.customer, total_amount=Decimal('200'),
            delivery_fee=Decimal('100'), shipping_address='A real address',
            shipping_city='kathmandu', phone='9800000000', notes='',
        )
        OrderItem.objects.create(
            order=real, product=self.product, product_name=self.product.name,
            quantity=2, price=self.product.price,
        )
        self.product.stock -= 2
        self.product.popularity_score += 2
        self.product.save(update_fields=['stock', 'popularity_score'])

        self._purge()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 98)
        self.assertEqual(self.product.popularity_score, 7)


class PurgeUserCascadeTests(StatusHistoryTestBase):
    """Deleting a probe account must not leave its orders' effects in the catalogue.

    `Order.user` is `CASCADE`, so `purge_verification_users` deletes a probe account's
    orders as a side effect. That happened *after* `purge_verification_orders` had run its
    own reversal, so those orders' reservations were never released — the third path with
    the same flaw as cancelling an order and deleting one. Every verifier that registers
    an account leaked stock and accumulated demand signal.
    """

    def _probe(self, username, quantity=3, status='pending'):
        from accounts.models import UserProfile

        user = User.objects.create_user(username, password='pw12345678')
        UserProfile.objects.create(user=user, role=ROLE_CUSTOMER)

        order = Order.objects.create(
            user=user, total_amount=Decimal('300'), delivery_fee=Decimal('100'),
            shipping_address='Probe address', shipping_city='kathmandu',
            phone='9800000000', status=status, notes='',
        )
        OrderItem.objects.create(
            order=order, product=self.product, product_name=self.product.name,
            quantity=quantity, price=self.product.price,
        )
        self.product.stock -= quantity
        self.product.popularity_score += quantity
        self.product.save(update_fields=['stock', 'popularity_score'])
        return user, order

    def _purge_users(self, *args):
        from django.core.management import call_command
        from io import StringIO
        out = StringIO()
        call_command('purge_verification_users', *args, stdout=out)
        return out.getvalue()

    def test_deleting_a_probe_account_returns_its_orders_stock(self):
        self._probe('verifyday13cascade')
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.popularity_score), (97, 8))

        self._purge_users()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100,
                         'the cascaded order left its stock reservation behind')
        self.assertEqual(self.product.popularity_score, 5,
                         'the cascaded order kept its demand signal')
        self.assertFalse(User.objects.filter(username='verifyday13cascade').exists())

    def test_a_cancelled_probe_order_does_not_double_release_stock(self):
        self._probe('verifyday13cancel', quantity=4, status='cancelled')
        # Cancelling would have released stock; simulate that having happened.
        self.product.stock += 4
        self.product.save(update_fields=['stock'])
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100)

        self._purge_users()

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 100, 'stock was returned twice')
        self.assertEqual(self.product.popularity_score, 5,
                         'a cancelled probe order kept its demand signal')

    def test_no_restock_leaves_the_catalogue_alone(self):
        self._probe('verifyday13nostock')
        self._purge_users('--no-restock')

        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.popularity_score), (97, 8))

    def test_protected_accounts_are_never_deleted(self):
        """The prefix match must never reach the demo logins.

        The protected accounts are **established here first**, with `get_or_create` —
        `vendor1` already exists in a fresh test database, because the data migration
        `products.0003_seed_areas_and_vendor` creates it. Two versions of this test were
        wrong before this one: the first asserted that `admin` survived a purge when
        `admin` had never been created (a precondition it did not own), and the second
        used `create_user`, which collided with the migration's `vendor1`.
        """
        from accounts.models import UserProfile

        for username in ('admin', 'testuser', 'vendor1'):
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password('pw12345678')
                user.save()
                UserProfile.objects.create(user=user, role=ROLE_CUSTOMER)
        self._probe('verifyday13protected')

        self._purge_users()

        for username in ('admin', 'testuser', 'vendor1'):
            self.assertTrue(User.objects.filter(username=username).exists(),
                            f'{username} was deleted by the purge')
        self.assertFalse(User.objects.filter(username='verifyday13protected').exists())

    def test_a_real_accounts_orders_are_untouched(self):
        """A non-probe account and its order must survive, catalogue included."""
        real = Order.objects.create(
            user=self.customer, total_amount=Decimal('200'),
            delivery_fee=Decimal('100'), shipping_address='A real address',
            shipping_city='kathmandu', phone='9800000000', notes='',
        )
        OrderItem.objects.create(
            order=real, product=self.product, product_name=self.product.name,
            quantity=2, price=self.product.price,
        )
        self.product.stock -= 2
        self.product.popularity_score += 2
        self.product.save(update_fields=['stock', 'popularity_score'])

        self._purge_users()

        self.assertTrue(Order.objects.filter(pk=real.pk).exists())
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock, self.product.popularity_score), (98, 7))


class MockedPaymentDisclosureTests(StatusHistoryTestBase):
    """A simulated gateway must say so, everywhere a customer can see it.

    The demo marks an `esewa`/`khalti` order paid and confirmed without contacting
    anything. That shortcut is fine; presenting it as a completed transaction is not,
    and it is the same rule the forecast page already follows for synthetic data.

    These tests pin the disclosure to the **single constant** that decides it, so
    flipping `PAYMENT_METHODS_ARE_MOCKED` when a real integration lands cannot leave
    a stale "Simulated" label behind — or a missing one.
    """

    def setUp(self):
        super().setUp()
        self.customer_client = self.api(self.customer)

    def _checkout(self, payment_method, extra=None):
        Cart.objects.create(user=self.customer, product=self.product, quantity=1)
        payload = {
            'shipping_address': 'Test Tole, Kathmandu',
            'shipping_city': 'kathmandu',
            'phone': '9800000000',
            'payment_method': payment_method,
        }
        payload.update(extra or {})
        return self.customer_client.post('/api/orders/checkout/', payload, format='json')

    def test_the_config_lists_every_method_with_its_honesty_flag(self):
        response = self.customer_client.get('/api/orders/config/')
        self.assertEqual(response.status_code, 200)
        methods = {m['value']: m for m in response.data['payment_methods']}
        self.assertEqual(set(methods), {'cod', 'esewa', 'khalti'})
        self.assertFalse(methods['cod']['is_mocked'])
        self.assertTrue(methods['esewa']['is_mocked'])
        self.assertTrue(methods['khalti']['is_mocked'])

    def test_the_config_reports_that_something_is_mocked(self):
        response = self.customer_client.get('/api/orders/config/')
        self.assertTrue(response.data['any_payment_mocked'])

    def test_a_mocked_order_is_flagged_on_the_order_itself(self):
        order_id = self._checkout('esewa').data['id']
        detail = self.customer_client.get(f'/api/orders/{order_id}/')
        self.assertTrue(detail.data['payment_is_mocked'])

    def test_a_cod_order_is_not_flagged_as_mocked(self):
        """Cash on delivery is genuinely collected, so it must not carry the label."""
        order_id = self._checkout('cod').data['id']
        detail = self.customer_client.get(f'/api/orders/{order_id}/')
        self.assertFalse(detail.data['payment_is_mocked'])

    def test_the_status_history_records_that_no_money_moved(self):
        """The timeline is the audit trail — it must not read as a real payment."""
        order_id = self._checkout('esewa').data['id']
        note = OrderStatusEvent.objects.get(
            order_id=order_id, to_status='confirmed',
        ).note
        self.assertIn('simulated', note.lower())
        self.assertIn('no money', note.lower())

    def test_the_customer_cannot_forge_the_flag(self):
        """`payment_is_mocked` is derived, never accepted from the client."""
        response = self._checkout('esewa', extra={'payment_is_mocked': False})
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data['payment_is_mocked'])
