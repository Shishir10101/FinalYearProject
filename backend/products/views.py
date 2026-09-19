from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend
from .models import Area, Category, Product, Vendor
from .serializers import (
    AreaSerializer, VendorSerializer,
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    ProductAdminSerializer, CategoryAdminSerializer,
)
from core.permissions import (
    IsStaffRole, IsManagerOrReadOnly, is_manager, is_vendor, vendor_for,
)


class CategoryListView(generics.ListAPIView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class CategoryProductsView(generics.ListAPIView):
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        slug = self.kwargs['slug']
        return Product.objects.filter(category__slug=slug, is_active=True)


class ProductListView(generics.ListAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_featured']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'popularity_score', 'created_at', 'name']


class ProductDetailView(generics.RetrieveAPIView):
    queryset = Product.objects.filter(is_active=True)
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'


class FeaturedProductsView(generics.ListAPIView):
    queryset = Product.objects.filter(is_active=True, is_featured=True)[:8]
    serializer_class = ProductListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


# --- Admin Views ---

class AdminProductListCreateView(generics.ListCreateAPIView):
    """Catalogue management.

    * Admins/Super Admins: the whole catalogue, full write access.
    * Vendors: only their own products. ``get_queryset`` filters by ownership,
      so a vendor cannot even enumerate another vendor's items, and a crafted
      request for a foreign id returns 404 rather than 403 (no existence leak).
    """
    serializer_class = ProductAdminSerializer
    permission_classes = [IsStaffRole]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['category', 'is_featured', 'is_active', 'vendor']
    search_fields = ['name', 'description']
    ordering_fields = ['price', 'stock', 'popularity_score', 'created_at']

    def get_queryset(self):
        qs = Product.objects.select_related('category', 'vendor')
        if is_manager(self.request.user):
            return qs
        vendor = vendor_for(self.request.user)
        if vendor is None:
            return qs.none()
        return qs.filter(vendor=vendor)

    def perform_create(self, serializer):
        # A vendor's new products are always attributed to that vendor — they
        # cannot create catalogue items owned by someone else.
        if is_vendor(self.request.user):
            serializer.save(vendor=vendor_for(self.request.user))
        else:
            serializer.save()


class AdminProductDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProductAdminSerializer
    permission_classes = [IsStaffRole]

    def get_queryset(self):
        qs = Product.objects.select_related('category', 'vendor')
        if is_manager(self.request.user):
            return qs
        vendor = vendor_for(self.request.user)
        if vendor is None:
            return qs.none()
        return qs.filter(vendor=vendor)


class AdminCategoryListCreateView(generics.ListCreateAPIView):
    """Categories are shared taxonomy — vendors may read, only managers may write."""
    queryset = Category.objects.all()
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class AdminCategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Category.objects.all()
    serializer_class = CategoryAdminSerializer
    permission_classes = [IsManagerOrReadOnly]


# --- Area management ---

class AreaListView(generics.ListAPIView):
    """Public: the storefront needs the list of deliverable areas."""
    queryset = Area.objects.filter(is_active=True)
    serializer_class = AreaSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class AdminAreaListCreateView(generics.ListCreateAPIView):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class AdminAreaDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Area.objects.all()
    serializer_class = AreaSerializer
    permission_classes = [IsManagerOrReadOnly]


# --- Vendor management (Super Admin only for writes) ---

class AdminVendorListCreateView(generics.ListCreateAPIView):
    queryset = Vendor.objects.select_related('user', 'area')
    serializer_class = VendorSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        # A vendor may only see their own record.
        if is_vendor(self.request.user):
            vendor = vendor_for(self.request.user)
            return qs.filter(pk=vendor.pk) if vendor else qs.none()
        return qs


class AdminVendorDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Read: any manager. Write/delete: manager only.

    Note this was previously ``IsSuperAdmin``, which disagreed with the list
    view's ``IsStaffRole`` — an ADMIN could see a vendor in the list and then
    get a 403 the moment they opened it. Both views now share
    ``IsManagerOrReadOnly`` so the pair is coherent.
    """
    queryset = Vendor.objects.select_related('user', 'area')
    serializer_class = VendorSerializer
    permission_classes = [IsManagerOrReadOnly]

    def get_queryset(self):
        qs = super().get_queryset()
        if is_vendor(self.request.user):
            vendor = vendor_for(self.request.user)
            return qs.filter(pk=vendor.pk) if vendor else qs.none()
        return qs

