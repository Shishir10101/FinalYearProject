from rest_framework import serializers
from .models import Cart, Order, OrderItem
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

    class Meta:
        model = Order
        fields = ['id', 'total_amount', 'subtotal', 'delivery_fee', 'status', 'status_display',
                  'payment_method', 'payment_method_display', 'payment_status',
                  'shipping_address', 'shipping_city', 'phone', 'notes',
                  'items', 'timeline', 'created_at']
        read_only_fields = ['total_amount', 'status', 'payment_status']

    def get_timeline(self, obj):
        """Progress steps for the customer-facing order tracker.

        Derived from ``status`` rather than a separate history table. That is a
        deliberate trade-off: it is accurate for the current state but cannot show
        *when* each step happened, because nothing records those timestamps. A
        real deployment should add an ``OrderStatusEvent`` table; doing so now
        would add a migration and a write path for a demo that only needs to show
        where an order currently stands.

        ``cancelled`` is terminal and does not fit a linear progression, so it is
        returned as a single-step timeline.
        """
        if obj.status == 'cancelled':
            return {
                'steps': [
                    {'key': 'pending', 'label': 'Order Placed', 'state': 'done'},
                    {'key': 'cancelled', 'label': 'Cancelled', 'state': 'cancelled'},
                ],
                'current': 'cancelled',
                'is_terminal': True,
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
            steps.append({'key': key, 'label': label, 'state': state})

        return {
            'steps': steps,
            'current': obj.status,
            'is_terminal': is_finished,
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
