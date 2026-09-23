from rest_framework import serializers
from .models import (
    Cart, Order, OrderItem, ORDER_STATUS_CHOICES, PAYMENT_METHODS_ARE_MOCKED,
)
from products.models import Area
from products.serializers import ProductListSerializer


class CartSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source='product', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Cart
        fields = ['id', 'product', 'product_detail', 'quantity', 'subtotal']


class CartAddSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(default=1, min_value=1)


class CartUpdateSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'product_name', 'quantity', 'price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    subtotal = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    timeline = serializers.SerializerMethodField()
    # Whether the gateway named by `payment_method` actually took any money.
    # Published so the confirmation screen can say "demo mode" instead of letting a
    # `paid` status imply a real transaction. Derived from the single constant in
    # `models.py`, never re-listed here — see PAYMENT_METHODS_ARE_MOCKED.
    payment_is_mocked = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = ['id', 'total_amount', 'subtotal', 'delivery_fee', 'status', 'status_display',
                  'payment_method', 'payment_method_display', 'payment_status',
                  'payment_is_mocked',
                  'shipping_address', 'shipping_city', 'phone', 'notes',
                  'items', 'timeline', 'created_at']
        read_only_fields = ['total_amount', 'status', 'payment_status', 'payment_is_mocked']

    def get_payment_is_mocked(self, obj):
        return bool(PAYMENT_METHODS_ARE_MOCKED.get(obj.payment_method, False))

    def get_timeline(self, obj):
        """Progress steps for the customer-facing order tracker.

        Each step carries an ``at`` timestamp taken from a real
        ``OrderStatusEvent`` row, so the tracker can say *when* an order was
        confirmed, packed, dispatched and delivered — not merely where it stands
        now. Before ``OrderStatusEvent`` existed the timeline was derived from
        ``Order.status`` alone and every step was permanently undated.

        ``at`` is ``None`` for a step with no recorded event, which the UI renders
        as "not recorded". Orders placed before status tracking was introduced
        have a single backfilled event, so their earlier steps legitimately have
        no timestamp. Borrowing ``created_at`` for those would be inventing a
        delivery date.

        The one honest exception is ``pending``: an order *was* necessarily placed
        at ``Order.created_at``, so that value is used when no event records it.

        ``cancelled`` is terminal and does not fit a linear progression, so it is
        returned as its own two-step timeline.
        """
        events = list(obj.status_events.all())

        # Earliest moment each status was reached. `setdefault` (not assignment)
        # so a status that is somehow reached twice keeps its first timestamp.
        reached_at = {}
        for event in events:
            reached_at.setdefault(event.to_status, event.created_at)

        status_labels = dict(ORDER_STATUS_CHOICES)
        history = [
            {
                'status': event.to_status,
                'label': status_labels.get(event.to_status, event.to_status),
                'at': event.created_at,
            }
            for event in events
        ]

        if obj.status == 'cancelled':
            return {
                'steps': [
                    {'key': 'pending', 'label': 'Order Placed', 'state': 'done',
                     'at': reached_at.get('pending') or obj.created_at},
                    {'key': 'cancelled', 'label': 'Cancelled', 'state': 'cancelled',
                     'at': reached_at.get('cancelled')},
                ],
                'current': 'cancelled',
                'is_terminal': True,
                'history': history,
            }

        steps_def = [
            ('pending', 'Order Placed'),
            ('confirmed', 'Confirmed'),
            ('processing', 'Preparing'),
            ('shipped', 'Out for Delivery'),
            ('delivered', 'Delivered'),
        ]
        order_of = {key: i for i, (key, _) in enumerate(steps_def)}
        current_index = order_of.get(obj.status, 0)
        # A delivered order is finished, not "in progress". Without this the last
        # step stays marked `current` forever, so a completed order looks like it
        # is still moving — the customer-facing equivalent of a stuck spinner.
        is_finished = obj.status == 'delivered'

        steps = []
        for i, (key, label) in enumerate(steps_def):
            if i < current_index or (is_finished and i == current_index):
                state = 'done'
            elif i == current_index:
                state = 'current'
            else:
                state = 'upcoming'
            at = reached_at.get(key)
            if at is None and key == 'pending':
                at = obj.created_at
            steps.append({'key': key, 'label': label, 'state': state, 'at': at})

        return {
            'steps': steps,
            'current': obj.status,
            'is_terminal': is_finished,
            'history': history,
        }


class CheckoutSerializer(serializers.Serializer):
    """Validates a checkout request.

    ``shipping_city`` is validated against the **live** ``Area`` table rather than
    a hardcoded list. It previously read
    ``ChoiceField(choices=['kathmandu', 'lalitpur', 'bhaktapur'])``, which meant an
    area added through Catalog Settings was accepted by the admin UI and then
    rejected at checkout — the new ``Area`` model would have been decorative.
    """

    shipping_address = serializers.CharField()
    shipping_city = serializers.SlugRelatedField(
        slug_field='slug',
        queryset=Area.objects.filter(is_active=True),
        error_messages={
            'does_not_exist': 'We do not deliver to that area yet.',
            'invalid': 'Please choose a delivery area.',
        },
    )
    phone = serializers.CharField(max_length=15)
    payment_method = serializers.ChoiceField(choices=['cod', 'esewa', 'khalti'])
    notes = serializers.CharField(required=False, allow_blank=True, default='')


class AdminOrderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = ['status', 'payment_status']
