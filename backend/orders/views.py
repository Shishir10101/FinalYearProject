from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.db import transaction
from .models import (
    Cart, Order, OrderItem, OrderStatusEvent,
    PAYMENT_METHOD_CHOICES, PAYMENT_METHODS_ARE_MOCKED,
)
from products.models import Area, Product
from core.permissions import IsStaffRole, is_manager, vendor_for
from .serializers import (
    CartSerializer, CartAddSerializer, CartUpdateSerializer,
    OrderSerializer, CheckoutSerializer, AdminOrderUpdateSerializer
)

DELIVERY_FEE = settings.DELIVERY_FEE


def get_delivery_fee():
    """Flat delivery charge applied to every order, in NPR."""
    return DELIVERY_FEE


def release_order_stock(order):
    """Return a cancelled order's units to inventory. Returns the units restored.

    Stock is **reserved** when an order is placed — `CheckoutView` decrements
    `product.stock` for every line — and nothing ever released it. Cancelling an order
    therefore leaked inventory permanently: the goods are back on the shelf, but the
    system still counts them as gone. Measured on this project's own data, that had
    already cost **538 units across 23 products**, which in turn produced false
    low-stock and restock alerts — the demand-prediction feature reporting on inventory
    that does not exist.

    `OrderItem.product` is nullable (`SET_NULL`), so a line whose product has since been
    deleted is skipped: there is no row left to return stock to. That is the correct
    behaviour rather than a 500 — the order stays cancellable.

    **`popularity_score` is deliberately not adjusted.** It records that a product was
    asked for, not that money changed hands, so it stays monotonic; `stock` is a factual
    count of what is on the shelf and must be exact. The two are not symmetric.
    """
    restored = 0
    for item in order.items.select_related('product'):
        product = item.product
        if product is None:
            continue
        product.stock += item.quantity
        product.save(update_fields=['stock'])
        restored += item.quantity
    return restored


def reserve_order_stock(order):
    """Re-take a reinstated order's units. Returns a list of shortfalls.

    The inverse of `release_order_stock`, for when a cancelled order is moved back into
    an active status. If any line can no longer be covered, the caller must abort — a
    partial reservation would silently under-count stock, which is the same class of bug
    in the other direction. The caller wraps this in `transaction.atomic`, so raising
    rolls back the lines already taken.
    """
    shortfalls = []
    for item in order.items.select_related('product'):
        product = item.product
        if product is None:
            continue
        if product.stock < item.quantity:
            shortfalls.append({
                'product': product.name,
                'available': product.stock,
                'needed': item.quantity,
            })
            continue
        product.stock -= item.quantity
        product.save(update_fields=['stock'])
    return shortfalls


def reverse_order_popularity(order):
    """Undo the demand signal a **fixture** order contributed. Returns points removed.

    `popularity_score` is only ever incremented, by `CheckoutView`. Cancellation
    deliberately does *not* reverse it, because a cancelled order still represents a
    customer asking for something.

    A **verification** order represents nobody. That distinction is the whole point of
    this function: the field feeds the recommendation engine's popularity bonus
    (`festivals/recommender.py`), the trending list, the default catalogue ordering and
    the search tie-break — so fixture traffic left in place means the demo recommends
    whatever the test suite happened to buy. Left unchecked it had reached **591 points
    across 23 products**, with one product at 256 against a seeded 98.

    Floored at zero: `popularity_score` is a `PositiveIntegerField`, so an unguarded
    subtraction would raise `IntegrityError` on a product whose score was already reset
    below the quantity being reversed.
    """
    removed = 0
    for item in order.items.select_related('product'):
        product = item.product
        if product is None:
            continue
        taken = min(item.quantity, product.popularity_score)
        if taken:
            product.popularity_score -= taken
            product.save(update_fields=['popularity_score'])
            removed += taken
    return removed


class StoreConfigView(APIView):
    """Public storefront configuration shared by both frontends.

    Keeps the delivery fee out of frontend source so the amount shown in the
    cart, the checkout button, and the saved order can never disagree.

    Delivery areas are included with their fee overrides so the checkout page can
    show the correct total for the area as soon as it is chosen, rather than
    discovering a different amount after the order is placed.

    Payment methods are served from here for the same reason, and because the
    checkout form has to tell the customer the truth about them *before* they
    choose one. Every digital method is currently mocked — see
    ``PAYMENT_METHODS_ARE_MOCKED`` — and a demo that quietly reports a paid order
    with no gateway behind it is the one thing this project must not do.
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        default_fee = float(get_delivery_fee())
        areas = [
            {
                'id': area.id,
                'name': area.name,
                'slug': area.slug,
                'district': area.district,
                'delivery_fee': float(area.delivery_fee) if area.delivery_fee is not None else default_fee,
                'is_override': area.delivery_fee is not None,
            }
            for area in Area.objects.filter(is_active=True)
        ]
        return Response({
            'delivery_fee': default_fee,
            'free_delivery_threshold': None,  # reserved; no free-delivery rule yet
            'currency': 'NPR',
            'areas': areas,
            'payment_methods': [
                {
                    'value': value,
                    'label': label,
                    'is_mocked': bool(PAYMENT_METHODS_ARE_MOCKED.get(value, False)),
                }
                for value, label in PAYMENT_METHOD_CHOICES
            ],
            # A single flag the UI can use for one banner, rather than asking it to
            # re-derive "some methods are fake" from the list each time.
            'any_payment_mocked': any(PAYMENT_METHODS_ARE_MOCKED.values()),
        })


class CartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        cart_items = Cart.objects.filter(user=request.user).select_related('product', 'product__category')
        serializer = CartSerializer(cart_items, many=True)
        subtotal = sum(item.subtotal for item in cart_items)
        delivery_fee = get_delivery_fee() if cart_items else 0
        total_quantity = sum(item.quantity for item in cart_items)
        return Response({
            'items': serializer.data,
            'subtotal': subtotal,
            'delivery_fee': delivery_fee,
            'total': subtotal + delivery_fee,
            'count': total_quantity
        })


class CartAddView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CartAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        product_id = serializer.validated_data['product_id']
        quantity = serializer.validated_data['quantity']

        try:
            product = Product.objects.get(id=product_id, is_active=True)
        except Product.DoesNotExist:
            return Response({'error': 'Product not found'}, status=status.HTTP_404_NOT_FOUND)

        if product.stock < quantity:
            return Response({'error': 'Insufficient stock'}, status=status.HTTP_400_BAD_REQUEST)

        cart_item, created = Cart.objects.get_or_create(
            user=request.user, product=product,
            defaults={'quantity': quantity}
        )
        if not created:
            cart_item.quantity += quantity
            cart_item.save()

        return Response({'message': 'Added to cart', 'quantity': cart_item.quantity},
                        status=status.HTTP_200_OK)


class CartUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def put(self, request, pk):
        serializer = CartUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cart_item = Cart.objects.get(id=pk, user=request.user)
        except Cart.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)

        quantity = serializer.validated_data['quantity']
        if cart_item.product.stock < quantity:
            return Response({'error': 'Insufficient stock'}, status=status.HTTP_400_BAD_REQUEST)

        cart_item.quantity = quantity
        cart_item.save()
        return Response({'message': 'Cart updated', 'quantity': cart_item.quantity})


class CartRemoveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk):
        try:
            cart_item = Cart.objects.get(id=pk, user=request.user)
            cart_item.delete()
            return Response({'message': 'Item removed from cart'})
        except Cart.DoesNotExist:
            return Response({'error': 'Cart item not found'}, status=status.HTTP_404_NOT_FOUND)


class CartAddKitView(APIView):
    """Add all items from a festival kit to cart"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, kit_id):
        from festivals.models import FestivalKit
        try:
            kit = FestivalKit.objects.get(id=kit_id, is_active=True)
        except FestivalKit.DoesNotExist:
            return Response({'error': 'Kit not found'}, status=status.HTTP_404_NOT_FOUND)

        kit_items = kit.items.select_related('product')
        added = 0
        for kit_item in kit_items:
            product = kit_item.product
            if product.is_active and product.stock >= kit_item.quantity:
                cart_item, created = Cart.objects.get_or_create(
                    user=request.user, product=product,
                    defaults={'quantity': kit_item.quantity}
                )
                if not created:
                    cart_item.quantity += kit_item.quantity
                    cart_item.save()
                added += 1

        return Response({'message': f'{added} items added to cart from kit "{kit.name}"'})


class CartAddPujaView(APIView):
    """Add every product a ritual calls for.

    Mirrors ``CartAddKitView``, but driven by the ritual's own item list rather
    than a kit's — which is the point of having Puja as a separate discovery
    entry point: a shopper can shop by ceremony even when no kit exists for it.

    Only *required* items are added. Optional extras are a merchandising choice,
    and silently putting them in the cart would be putting words in the
    customer's mouth.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, puja_id):
        from festivals.models import Puja
        try:
            puja = Puja.objects.get(id=puja_id, is_active=True)
        except Puja.DoesNotExist:
            return Response({'error': 'Ritual not found'}, status=status.HTTP_404_NOT_FOUND)

        added = 0
        skipped = []
        for puja_item in puja.items.select_related('product').filter(is_required=True):
            product = puja_item.product
            if not product.is_active or product.stock < puja_item.quantity:
                # Report what was left out instead of quietly adding a short order.
                skipped.append(product.name)
                continue

            cart_item, created = Cart.objects.get_or_create(
                user=request.user, product=product,
                defaults={'quantity': puja_item.quantity}
            )
            if not created:
                cart_item.quantity += puja_item.quantity
                cart_item.save()
            added += 1

        payload = {
            'message': f'{added} items added to cart for "{puja.name}"',
            'added': added,
        }
        if skipped:
            payload['skipped'] = skipped
            payload['warning'] = (
                'Some items could not be added because they are out of stock: '
                + ', '.join(skipped)
            )
        return Response(payload)


class CheckoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        cart_items = Cart.objects.filter(user=request.user).select_related('product')
        if not cart_items.exists():
            return Response({'error': 'Cart is empty'}, status=status.HTTP_400_BAD_REQUEST)

        # Validate stock and active status before calculating total and creating order
        for item in cart_items:
            if not item.product.is_active:
                return Response({'error': f'Item {item.product.name} is no longer available'}, status=status.HTTP_400_BAD_REQUEST)
            if item.product.stock < item.quantity:
                return Response(
                    {'error': f'Insufficient stock for {item.product.name}. Only {item.product.stock} left.'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

        # Calculate total: items + delivery fee.
        # The delivery fee is part of what the customer is charged, so it must be
        # persisted in Order.total_amount rather than added only at display time.
        # An Area may override the store-wide fee; the override is honoured here so
        # the Settings page actually changes what a customer is charged.
        area = serializer.validated_data['shipping_city']
        subtotal = sum(item.subtotal for item in cart_items)
        delivery_fee = area.delivery_fee if area.delivery_fee is not None else get_delivery_fee()
        total = subtotal + delivery_fee

        # Create order
        order = Order.objects.create(
            user=request.user,
            total_amount=total,
            delivery_fee=delivery_fee,
            shipping_address=serializer.validated_data['shipping_address'],
            shipping_city=area.slug,
            phone=serializer.validated_data['phone'],
            payment_method=serializer.validated_data['payment_method'],
            notes=serializer.validated_data.get('notes', ''),
        )

        # Create order items and update stock
        for cart_item in cart_items:
            OrderItem.objects.create(
                order=order,
                product=cart_item.product,
                product_name=cart_item.product.name,
                quantity=cart_item.quantity,
                price=cart_item.product.price,
            )
            # Decrease stock
            cart_item.product.stock -= cart_item.quantity
            cart_item.product.popularity_score += cart_item.quantity
            cart_item.product.save()

        # Clear cart
        cart_items.delete()

        # Record the order's history from its very first moment, so the customer
        # tracker can date every step instead of only showing the current one.
        OrderStatusEvent.record(
            order, 'pending', from_status='', changed_by=request.user,
            note='Order placed by the customer.',
        )

        # Payment. Every digital method is currently mocked: this marks the order paid
        # and confirmed with no gateway involved. That is a deliberate demo shortcut
        # (see PAYMENT_METHODS_ARE_MOCKED), and the order records it as such in its own
        # history, so the tracker cannot later be read as evidence that money moved.
        #
        # The status is still advanced to `confirmed` rather than left at `pending`,
        # because that is what makes the rest of the demo flow coherent — the point is
        # to be honest about the payment, not to make the order unusable.
        if order.payment_method in ['esewa', 'khalti']:
            is_mocked = PAYMENT_METHODS_ARE_MOCKED.get(order.payment_method, False)
            order.payment_status = 'paid'
            order.status = 'confirmed'
            order.save()
            OrderStatusEvent.record(
                order, 'confirmed', from_status='pending', changed_by=request.user,
                note=(
                    f'{order.get_payment_method_display()} payment simulated — '
                    'no gateway was contacted and no money was taken.'
                    if is_mocked else
                    f'{order.get_payment_method_display()} payment received.'
                ),
            )

        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)


class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items', 'status_events')


class OrderDetailView(generics.RetrieveAPIView):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related('items', 'status_events')


# --- Admin Views ---

class AdminOrderListView(generics.ListAPIView):
    """Order management for the dashboard.

    Vendors see only orders containing at least one of their products — they
    have no business reading another supplier's customer addresses. The filter
    is applied in the queryset, not the UI, so a hand-crafted request cannot
    bypass it.
    """
    serializer_class = OrderSerializer
    permission_classes = [IsStaffRole]

    def get_queryset(self):
        qs = Order.objects.all().prefetch_related('items', 'status_events').select_related('user')
        if is_manager(self.request.user):
            return qs
        vendor = vendor_for(self.request.user)
        if vendor is None:
            return qs.none()
        return qs.filter(items__product__vendor=vendor).distinct()


class AdminOrderUpdateView(generics.UpdateAPIView):
    serializer_class = AdminOrderUpdateSerializer
    permission_classes = [IsStaffRole]

    def get_queryset(self):
        qs = Order.objects.all()
        if is_manager(self.request.user):
            return qs
        vendor = vendor_for(self.request.user)
        if vendor is None:
            return qs.none()
        return qs.filter(items__product__vendor=vendor).distinct()

    @transaction.atomic
    def perform_update(self, serializer):
        """Persist the change, move stock, and append a status-history row.

        The event is written only for a genuine transition. Saving the same status
        back (or changing only ``payment_status``) must not litter the history with
        duplicate entries, otherwise the customer's timeline fills up with
        meaningless repeated steps.

        **Stock moves with the status.** Cancelling returns the order's units to
        inventory; moving a cancelled order back into an active status re-takes them.
        Both are guarded on `previous_status` so a repeated save cannot restore the same
        units twice — the idempotency matters more than the happy path here, because a
        double restore inflates inventory just as silently as the original leak
        deflated it.

        The whole method is atomic, so a rejected re-reservation rolls back the lines it
        had already taken rather than leaving stock half-decremented.
        """
        order = self.get_object()
        previous_status = order.status
        updated = serializer.save()

        if updated.status == previous_status:
            return

        note = 'Status updated by staff.'

        if updated.status == 'cancelled':
            restored = release_order_stock(updated)
            note = (
                f'Order cancelled. {restored} unit(s) returned to stock.'
                if restored else 'Order cancelled.'
            )
        elif previous_status == 'cancelled':
            shortfalls = reserve_order_stock(updated)
            if shortfalls:
                # Raised inside the atomic block, so the partial decrements roll back.
                # Refusing is the right answer: reinstating an order the shop can no
                # longer fulfil would put a promise on the customer's timeline that
                # cannot be kept.
                detail = '; '.join(
                    f"{s['product']} needs {s['needed']} but only {s['available']} remain"
                    for s in shortfalls
                )
                raise ValidationError({
                    'status': (
                        f'Cannot reinstate this order — stock is no longer available. {detail}'
                    ),
                })
            note = 'Order reinstated. Stock re-reserved.'

        OrderStatusEvent.record(
            updated,
            updated.status,
            from_status=previous_status,
            changed_by=self.request.user,
            note=note,
        )
