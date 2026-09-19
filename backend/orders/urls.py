from django.urls import path
from .views import (
    StoreConfigView,
    CartView, CartAddView, CartUpdateView, CartRemoveView, CartAddKitView,
    CartAddPujaView,
    CheckoutView, OrderListView, OrderDetailView,
    AdminOrderListView, AdminOrderUpdateView
)

urlpatterns = [
    # Store configuration (public)
    path('config/', StoreConfigView.as_view(), name='store-config'),
    # Cart
    path('cart/', CartView.as_view(), name='cart'),
    path('cart/add/', CartAddView.as_view(), name='cart-add'),
    path('cart/update/<int:pk>/', CartUpdateView.as_view(), name='cart-update'),
    path('cart/remove/<int:pk>/', CartRemoveView.as_view(), name='cart-remove'),
    path('cart/add-kit/<int:kit_id>/', CartAddKitView.as_view(), name='cart-add-kit'),
    path('cart/add-puja/<int:puja_id>/', CartAddPujaView.as_view(), name='cart-add-puja'),
    # Checkout & Orders
    path('checkout/', CheckoutView.as_view(), name='checkout'),
    path('', OrderListView.as_view(), name='order-list'),
    path('<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    # Admin
    path('admin/orders/', AdminOrderListView.as_view(), name='admin-order-list'),
    path('admin/orders/<int:pk>/', AdminOrderUpdateView.as_view(), name='admin-order-update'),
]
