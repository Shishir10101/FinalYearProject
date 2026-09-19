from django.urls import path
from .views import (
    CategoryListView, CategoryProductsView, ProductListView,
    ProductDetailView, FeaturedProductsView, AreaListView,
    AdminProductListCreateView, AdminProductDetailView,
    AdminCategoryListCreateView, AdminCategoryDetailView,
    AdminAreaListCreateView, AdminAreaDetailView,
    AdminVendorListCreateView, AdminVendorDetailView,
)

urlpatterns = [
    # Public
    path('', ProductListView.as_view(), name='product-list'),
    path('featured/', FeaturedProductsView.as_view(), name='featured-products'),
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', CategoryProductsView.as_view(), name='category-products'),
    path('areas/', AreaListView.as_view(), name='area-list'),
    # ``ProductDetailView`` sets ``lookup_field = 'slug'``, so the detail route
    # must be slug-based. NOTE: this pattern was missing entirely — the view
    # existed and `ProductListSerializer` published a `slug`, but nothing routed
    # it, so the customer product page (which calls /products/<slug>/) 404'd on
    # every click. It must stay LAST among the public routes, otherwise a slug
    # like "featured" or "areas" would shadow those literal paths.
    path('<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
    # Admin
    path('admin/products/', AdminProductListCreateView.as_view(), name='admin-product-list'),
    path('admin/products/<int:pk>/', AdminProductDetailView.as_view(), name='admin-product-detail'),
    path('admin/categories/', AdminCategoryListCreateView.as_view(), name='admin-category-list'),
    path('admin/categories/<int:pk>/', AdminCategoryDetailView.as_view(), name='admin-category-detail'),
    path('admin/areas/', AdminAreaListCreateView.as_view(), name='admin-area-list'),
    path('admin/areas/<int:pk>/', AdminAreaDetailView.as_view(), name='admin-area-detail'),
    path('admin/vendors/', AdminVendorListCreateView.as_view(), name='admin-vendor-list'),
    path('admin/vendors/<int:pk>/', AdminVendorDetailView.as_view(), name='admin-vendor-detail'),
]
