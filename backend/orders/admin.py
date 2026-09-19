from django.contrib import admin
from .models import Cart, Order, OrderItem, OrderStatusEvent


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ['product_name', 'quantity', 'price']


class OrderStatusEventInline(admin.TabularInline):
    """Read-only: history is appended by the application, never hand-edited.

    Letting staff rewrite past events would defeat the point of having a record
    of what actually happened to an order.
    """
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    fields = ['created_at', 'from_status', 'to_status', 'note', 'changed_by']
    readonly_fields = fields
    ordering = ['created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'total_amount', 'status', 'payment_status', 'created_at']
    list_filter = ['status', 'payment_status', 'payment_method']
    inlines = [OrderItemInline, OrderStatusEventInline]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'quantity']


@admin.register(OrderStatusEvent)
class OrderStatusEventAdmin(admin.ModelAdmin):
    list_display = ['order', 'from_status', 'to_status', 'changed_by', 'created_at']
    list_filter = ['to_status']
    search_fields = ['order__id', 'note']
    readonly_fields = ['order', 'from_status', 'to_status', 'note', 'changed_by', 'created_at']

    def has_add_permission(self, request):
        return False

