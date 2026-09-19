from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from products.models import Product
from core.constants import CITY_CHOICES

ORDER_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('confirmed', 'Confirmed'),
    ('processing', 'Processing'),
    ('shipped', 'Shipped'),
    ('delivered', 'Delivered'),
    ('cancelled', 'Cancelled'),
]

PAYMENT_METHOD_CHOICES = [
    ('cod', 'Cash on Delivery'),
    ('esewa', 'eSewa'),
    ('khalti', 'Khalti'),
]

PAYMENT_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('paid', 'Paid'),
    ('failed', 'Failed'),
]


class Cart(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='cart_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} - {self.product.name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.product.price * self.quantity


class Order(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text='Delivery charge included in total_amount'
    )
    status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cod')
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')
    shipping_address = models.TextField()
    shipping_city = models.CharField(max_length=20, choices=CITY_CHOICES)
    phone = models.CharField(max_length=15)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def subtotal(self):
        """Item total before the delivery fee."""
        return self.total_amount - self.delivery_fee

    def __str__(self):
        return f"Order #{self.id} - {self.user.username}"


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    product_name = models.CharField(max_length=200)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x{self.quantity}"

    @property
    def subtotal(self):
        return self.price * self.quantity


class OrderStatusEvent(models.Model):
    """One recorded transition of an ``Order`` from one status to another.

    This exists because the order timeline used to be **derived** from
    ``Order.status``. That is enough to say where an order currently stands, but
    it can never say *when* it got there — the information simply was not stored
    anywhere, so "Shipped" was permanently undated. Every write path that changes
    a status now appends a row here instead.

    ``created_at`` uses ``default=timezone.now`` rather than ``auto_now_add``.
    That matters: ``auto_now_add`` ignores any value passed in, so the backfill
    migration for the pre-existing orders could not have preserved their real
    ``Order.created_at``. Same class of trap as the seed migrations that shipped
    a blank slug because historical models have no overridden ``save()``.

    Ordering is ``('created_at', 'id')`` — oldest first — with ``id`` breaking
    ties so two events written inside the same transaction still come back in a
    deterministic order.
    """

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_events')
    from_status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES, blank=True, default='')
    to_status = models.CharField(max_length=20, choices=ORDER_STATUS_CHOICES)
    note = models.CharField(max_length=255, blank=True, default='')
    changed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='order_status_changes',
        help_text='Staff member who made the change. NULL for customer-placed events.',
    )
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ['created_at', 'id']
        indexes = [models.Index(fields=['order', 'created_at'])]

    def __str__(self):
        return f"Order #{self.order_id}: {self.from_status or '(new)'} -> {self.to_status}"

    @classmethod
    def record(cls, order, to_status, *, from_status=None, changed_by=None, note='', at=None):
        """Append a status transition for ``order`` and return the new event.

        ``from_status`` defaults to the order's *current stored* status, which is
        what a caller almost always means. Pass it explicitly when the caller has
        already mutated ``order.status`` in memory, otherwise the "from" value
        would be recorded as the destination.
        """
        if from_status is None:
            from_status = order.status
        event = cls(
            order=order,
            from_status=from_status,
            to_status=to_status,
            changed_by=changed_by,
            note=note,
        )
        if at is not None:
            event.created_at = at
        event.save()
        return event

