from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.db import transaction
from .models import Cart, Order, OrderItem, OrderStatusEvent
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


class StoreConfigView(APIView):
    """Public storefront configuration shared by both frontends.

    Keeps the delivery fee out of frontend source so the amount shown in the
    cart, the checkout button, and the saved order can never disagree.

    Delivery areas are included with their fee overrides so the checkout page can
    show the correct total for the area as soon as it is chosen, rather than
    discovering a different amount after the order is placed.
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

        # Mock payment
        if order.payment_method in ['esewa', 'khalti']:
            order.payment_status = 'paid'
            order.status = 'confirmed'
            order.save()
            OrderStatusEvent.record(
                order, 'confirmed', from_status='pending', changed_by=request.user,
                note='Payment received (mocked gateway).',
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

    def perform_update(self, serializer):
        """Persist the change and append a status-history row when status moves.

        The event is written only for a genuine transition. Saving the same status
        back (or changing only ``payment_status``) must not litter the history with
        duplicate entries, otherwise the customer's timeline fills up with
        meaningless repeated steps.
        """
        order = self.get_object()
        previous_status = order.status
        updated = serializer.save()
        if updated.status != previous_status:
            OrderStatusEvent.record(
                updated,
                updated.status,
                from_status=previous_status,
                changed_by=self.request.user,
                note='Status updated by staff.',
            )
