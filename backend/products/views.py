from rest_framework import generics, permissions, filters, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Avg, Count, Q
from django_filters.rest_framework import DjangoFilterBackend
from .models import Area, Category, Product, Review, Vendor
from .serializers import (
    AreaSerializer, VendorSerializer,
    CategorySerializer, ProductListSerializer, ProductDetailSerializer,
    ProductAdminSerializer, CategoryAdminSerializer,
    ReviewSerializer, ReviewWriteSerializer, ReviewAdminSerializer,
)
from core.permissions import (
    IsStaffRole, IsManagerOrReadOnly, IsManager, is_manager, is_vendor, vendor_for,
    promote_to_vendor,
)


def with_review_summary(queryset):
    """Annotate a Product queryset with its approved-review summary.

    Aggregated in the database, once, rather than counted per row inside a
    serializer — the same N+1 trap the ritual list carries a test for. The
    ``filter=`` is what keeps unapproved reviews out of the public average; without
    it, hiding a review would change the product's rating and nobody would notice.

    ``Avg`` returns ``None`` when a product has no approved reviews, which is why the
    serializer declares ``allow_null=True`` rather than defaulting to 0 — a product
    with no reviews has no rating, and showing it as 0 stars would be a lie.
    """
    return queryset.annotate(
        average_rating=Avg('reviews__rating', filter=Q(reviews__is_approved=True)),
        review_count=Count('reviews', filter=Q(reviews__is_approved=True)),
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
    serializer_class = ProductDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return with_review_summary(Product.objects.filter(is_active=True))


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

    def perform_create(self, serializer):
        """Creating a shop also makes its account a vendor.

        A ``Vendor`` row points at an ordinary login. The row alone does not make
        that account a vendor — the **role** does, and until this existed nothing in
        the product could set it, so "Add a vendor" attached a shop to an account
        that still resolved as ``customer`` and could not open the dashboard.

        Deleting a vendor deliberately does **not** reverse this. Revoking a login's
        access is an account operation, not a shop operation, and conflating them
        would let removing a shop silently lock someone out of the dashboard. The
        delete confirmation says so.
        """
        vendor = serializer.save()
        promote_to_vendor(vendor.user)


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



# --- Reviews ----------------------------------------------------------------
#
# `docs/DATABASE-DESIGN.md` listed a `Review` table as a known omission ("not in
# scope; noted as post-MVP"). A product page with no social proof is the one gap
# every shopper notices, so it is the P1 item that was built first.


def has_purchased(user, product):
    """Whether this account had ordered this product before reviewing it.

    Local import on purpose: `orders` imports `products.models`, so importing
    `orders.models` at module scope here would be a cycle waiting to happen.
    """
    from orders.models import OrderItem

    return OrderItem.objects.filter(
        order__user=user, product=product,
    ).exclude(order__status='cancelled').exists()


def review_summary(product):
    """Approved-review aggregate for one product.

    `distribution` is the 5→1 histogram the storefront draws. Computed in one grouped
    query rather than five counts, and always over **approved** reviews so hiding one
    moves the average — which is the whole point of hiding it.
    """
    approved = product.reviews.filter(is_approved=True)
    agg = approved.aggregate(average=Avg('rating'), count=Count('id'))

    distribution = {str(stars): 0 for stars in range(5, 0, -1)}
    for row in approved.values('rating').annotate(total=Count('id')):
        distribution[str(row['rating'])] = row['total']

    return {
        'average_rating': round(agg['average'], 2) if agg['average'] is not None else None,
        'review_count': agg['count'],
        'distribution': distribution,
    }


def _product_for_reviews(slug):
    """A product reviews may be attached to, or None.

    Restricted to active products: reviewing something that is no longer sold would
    put a review on a page nobody can reach.
    """
    return Product.objects.filter(slug=slug, is_active=True).first()


class ProductReviewListCreateView(APIView):
    """One product's reviews.

    ``GET`` is public and returns approved reviews plus the summary the product page
    renders. It is **paginated** (unlike the admin editor lists, which are deliberately
    not): a review list is browsable content that grows, so `?page=` is the right
    shape. The summary is always computed over every approved review, never just the
    current page — a page-local average would change as you paginated, which is the
    kind of number that quietly makes a product look better or worse.

    ``POST`` is create-**or-update** for the signed-in reviewer. That is not a
    shortcut: `unique_together ('product', 'user')` means a second POST for the same
    product is an edit of your own review, and the alternative is a 400 that the UI
    would have to translate back into "edit your review".
    """

    permission_classes = [permissions.AllowAny]

    def get(self, request, slug):
        product = _product_for_reviews(slug)
        if product is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        queryset = (
            product.reviews.filter(is_approved=True)
            .select_related('user')
        )

        page = self._paginate(request, queryset)
        serializer = ReviewSerializer(page, many=True, context={'request': request})

        mine = None
        if request.user.is_authenticated:
            own = product.reviews.filter(user=request.user).first()
            if own is not None:
                mine = ReviewSerializer(own, context={'request': request}).data

        return Response({
            'summary': review_summary(product),
            'results': serializer.data,
            'count': queryset.count(),
            'mine': mine,
        })

    def _paginate(self, request, queryset):
        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        paginator.page_size = 12
        page = paginator.paginate_queryset(queryset, request, view=self)
        return page if page is not None else list(queryset)

    def post(self, request, slug):
        if not request.user.is_authenticated:
            return Response({'detail': 'Authentication credentials were not provided.'},
                            status=status.HTTP_401_UNAUTHORIZED)

        product = _product_for_reviews(slug)
        if product is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

        existing = Review.objects.filter(product=product, user=request.user).first()
        serializer = ReviewWriteSerializer(existing, data=request.data)
        serializer.is_valid(raise_exception=True)

        if existing is not None:
            review = serializer.save()
            created = False
        else:
            review = serializer.save(
                product=product,
                user=request.user,
                # Snapshot, not a live lookup — see the model docstring.
                is_verified_purchase=has_purchased(request.user, product),
            )
            created = True

        return Response(
            ReviewSerializer(review, context={'request': request}).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ReviewDetailView(generics.DestroyAPIView):
    """Delete a review.

    Your own, or any review if you are a manager — the same shape as the rest of the
    project's ownership rules. A customer deleting someone else's review gets a 404,
    because the queryset is filtered by owner rather than the permission class
    returning 403: no existence leak.
    """

    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Review.objects.select_related('product', 'user')
        if is_manager(self.request.user):
            return qs
        return qs.filter(user=self.request.user)


class AdminReviewListView(generics.ListAPIView):
    """Every review, including hidden ones. **Managers only.**

    A manager has to be able to see what they hid, otherwise `is_approved=False` is a
    one-way door. `?is_approved=0` / `=1` narrows it, and `?product=<id>` scopes it to
    one product.

    `pagination_class = None`, matching every other admin collection in this project
    (kits, rituals, vendors). That is not just consistency: paginated, a hidden review
    on page 2 would be invisible to the only person who can unhide it, which is the
    one-way door again. The **public** review list on a product page *is* paginated —
    that one is browsable content that grows.
    """

    serializer_class = ReviewAdminSerializer
    permission_classes = [IsManager]
    pagination_class = None

    def get_queryset(self):
        qs = Review.objects.select_related('product', 'user')

        approved = self.request.query_params.get('is_approved')
        if approved in ('0', 'false', 'False'):
            qs = qs.filter(is_approved=False)
        elif approved in ('1', 'true', 'True'):
            qs = qs.filter(is_approved=True)

        product_id = self.request.query_params.get('product')
        if product_id:
            qs = qs.filter(product_id=product_id)

        return qs


class AdminReviewDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Hide, unhide, or delete a review."""

    queryset = Review.objects.select_related('product', 'user')
    serializer_class = ReviewAdminSerializer
    permission_classes = [IsManager]
