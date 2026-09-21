from django.urls import path
from .views import (
    CategoryListView, CategoryProductsView, ProductListView, ProductSearchView,
    ProductDetailView, FeaturedProductsView, AreaListView,
    ProductReviewListCreateView, ReviewDetailView,
    AdminProductListCreateView, AdminProductDetailView,
    AdminCategoryListCreateView, AdminCategoryDetailView,
    AdminAreaListCreateView, AdminAreaDetailView,
    AdminVendorListCreateView, AdminVendorDetailView,
    AdminReviewListView, AdminReviewDetailView,
)

# Ordering here is load-bearing, and it is not the obvious order.
#
# Every literal-prefixed route comes first — including the whole `admin/` family —
# and the slug patterns come LAST. The reason is that `admin` is a perfectly valid
# slug, so a public pattern like `<slug:slug>/reviews/` will happily match
# `admin/reviews/` with `slug='admin'`, look for a product called "admin", find none
# and 404. The admin route below it then never runs.
#
# That is not hypothetical: it is exactly what happened when reviews were added. The
# admin review list returned 404 for a manager, and the tests caught it. The rule for
# this file is therefore stronger than "the slug detail route goes last" — it is
# "**nothing with a slug converter may sit above a literal path of the same depth**".
#
# Adding a route here? Put it with its family above, never above `product-detail`.
urlpatterns = [
    # --- Public literals ---
    path('', ProductListView.as_view(), name='product-list'),
    path('search/', ProductSearchView.as_view(), name='product-search'),
    path('featured/', FeaturedProductsView.as_view(), name='featured-products'),
    path('categories/', CategoryListView.as_view(), name='category-list'),
    path('categories/<slug:slug>/', CategoryProductsView.as_view(), name='category-products'),
    path('areas/', AreaListView.as_view(), name='area-list'),
    path('reviews/<int:pk>/', ReviewDetailView.as_view(), name='review-detail'),

    # --- Admin (literal `admin/` prefix, so it must precede the slug patterns) ---
    path('admin/products/', AdminProductListCreateView.as_view(), name='admin-product-list'),
    path('admin/products/<int:pk>/', AdminProductDetailView.as_view(), name='admin-product-detail'),
    path('admin/categories/', AdminCategoryListCreateView.as_view(), name='admin-category-list'),
    path('admin/categories/<int:pk>/', AdminCategoryDetailView.as_view(), name='admin-category-detail'),
    path('admin/areas/', AdminAreaListCreateView.as_view(), name='admin-area-list'),
    path('admin/areas/<int:pk>/', AdminAreaDetailView.as_view(), name='admin-area-detail'),
    path('admin/vendors/', AdminVendorListCreateView.as_view(), name='admin-vendor-list'),
    path('admin/vendors/<int:pk>/', AdminVendorDetailView.as_view(), name='admin-vendor-detail'),
    path('admin/reviews/', AdminReviewListView.as_view(), name='admin-review-list'),
    path('admin/reviews/<int:pk>/', AdminReviewDetailView.as_view(), name='admin-review-detail'),

    # --- Public slug patterns, LAST ---
    # ``ProductDetailView`` sets ``lookup_field = 'slug'``, so the detail route must
    # be slug-based. NOTE: this pattern was once missing entirely — the view existed
    # and `ProductListSerializer` published a `slug`, but nothing routed it, so the
    # customer product page 404'd on every click. It must stay below every literal
    # path, or a slug like "featured" or "areas" shadows them.
    path('<slug:slug>/reviews/', ProductReviewListCreateView.as_view(), name='product-reviews'),
    path('<slug:slug>/', ProductDetailView.as_view(), name='product-detail'),
]
