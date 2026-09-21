from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Count, Q
from django.utils import timezone
from datetime import timedelta
from .models import (
    FESTIVAL_CHOICES, FestivalKit, KitItem, UpcomingFestival, Puja, PujaItem,
)
from products.models import Product
from .serializers import (
    FestivalKitListSerializer, FestivalKitDetailSerializer,
    UpcomingFestivalSerializer, FestivalKitAdminSerializer,
    KitItemAdminSerializer, PujaListSerializer, PujaDetailSerializer,
    PujaAdminSerializer, PujaItemAdminSerializer,
)
from products.serializers import ProductListSerializer
from .recommender import Recommender, serialize_recommendations
from core.permissions import IsManagerOrReadOnly


class FestivalKitListView(generics.ListAPIView):
    queryset = FestivalKit.objects.filter(is_active=True)
    serializer_class = FestivalKitListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        qs = super().get_queryset()
        festival_type = self.request.query_params.get('festival_type')
        if festival_type:
            qs = qs.filter(festival_type=festival_type)
        return qs


class FestivalKitDetailView(generics.RetrieveAPIView):
    queryset = FestivalKit.objects.filter(is_active=True)
    serializer_class = FestivalKitDetailSerializer
    permission_classes = [permissions.AllowAny]


class UpcomingFestivalsView(generics.ListAPIView):
    """The festival calendar, soonest first.

    The result count used to be a hardcoded ``[:5]``, which meant the ten active
    upcoming festivals in the database could never all be reached — the storefront
    and the home page both silently showed the first five and there was no way to
    ask for the rest. It is now ``?limit=`` (default 5, capped at 50) so a caller
    that wants the whole calendar can get it.
    """

    serializer_class = UpcomingFestivalSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    DEFAULT_LIMIT = 5
    MAX_LIMIT = 50

    def get_limit(self):
        try:
            limit = int(self.request.query_params.get('limit', self.DEFAULT_LIMIT))
        except (TypeError, ValueError):
            return self.DEFAULT_LIMIT
        return max(1, min(limit, self.MAX_LIMIT))

    def get_queryset(self):
        today = timezone.now().date()
        return UpcomingFestival.objects.filter(
            date__gte=today,
            is_active=True
        )[:self.get_limit()]


class FestivalChoicesView(APIView):
    """The festival/ritual vocabulary, read straight from ``FESTIVAL_CHOICES``.

    The dashboard's kit and ritual forms both need the full enum to populate a
    select. Deriving it from the kits that happen to exist would be the same trap
    as the old hardcoded ``CITY_CHOICES``, only in reverse: a type with no kit yet
    would be missing from the dropdown, so the form could not create the first kit
    of a new type. The enum is the single source of truth and is published as-is.

    Public on purpose — every label here is already visible in the
    ``festival_type_display`` of the public kit list, so gating it would protect
    nothing.
    """

    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get(self, request):
        return Response([
            {'value': value, 'label': label} for value, label in FESTIVAL_CHOICES
        ])


class PujaListView(generics.ListAPIView):
    """Browse by ritual — the fourth discovery entry point.

    ``AGENTS.md`` §1 requires six entry points (Product · Category · Festival ·
    Puja · Samagri · Ready-made Kit). This one had no model, endpoint or page; the
    ``festival_type`` enum was doing double duty for festivals *and* rites of
    passage, and four of its seven used values (bratabandha, pasni, griha_pravesh,
    shraddha) are ceremonies rather than calendar events.

    No pagination: the ritual list is short and the storefront renders it as a
    single grid.
    """

    serializer_class = PujaListSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        # Counted in the database rather than per row, and `kits` prefetched so
        # `Puja.kit` reads the cache instead of querying once per puja.
        return (
            Puja.objects.filter(is_active=True)
            .annotate(
                item_count=Count('items', distinct=True),
                required_count=Count('items', filter=Q(items__is_required=True), distinct=True),
            )
            .prefetch_related('kits')
        )


class PujaDetailView(generics.RetrieveAPIView):
    """One ritual, with the samagri it calls for and its ready-made kit if any."""

    serializer_class = PujaDetailSerializer
    permission_classes = [permissions.AllowAny]
    lookup_field = 'slug'

    def get_queryset(self):
        return Puja.objects.filter(is_active=True).prefetch_related(
            'items__product__category', 'kits',
        )


class RecommendationsView(APIView):
    """Ranked, explainable "what do I need next?" recommendations.

    Ranking lives in ``festivals.recommender.Recommender`` so it can be unit
    tested. This view only handles HTTP concerns and serialization.

    Works for anonymous visitors (festival + popularity signals) and for
    authenticated shoppers (adds personalisation from order history).
    """
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            limit = int(request.query_params.get('limit', 12))
        except (TypeError, ValueError):
            limit = 12
        limit = max(1, min(limit, 48))

        result = Recommender(user=request.user).build(limit=limit)

        products = serialize_recommendations(
            result['recommended_products'], ProductListSerializer
        )
        upcoming = UpcomingFestivalSerializer(result['upcoming_festivals'], many=True)

        return Response({
            'upcoming_festivals': upcoming.data,
            'recommended_products': products,
            'meta': result['meta'],
            'message': (
                'Ranked by upcoming festival requirements, your past orders, '
                'and catalogue popularity.'
            ),
        })


# --- Admin Views ---

class AdminFestivalKitListCreateView(generics.ListCreateAPIView):
    queryset = FestivalKit.objects.all()
    serializer_class = FestivalKitAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class AdminFestivalKitDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = FestivalKit.objects.all()
    serializer_class = FestivalKitAdminSerializer
    permission_classes = [IsManagerOrReadOnly]


class AdminKitItemListCreateView(generics.ListCreateAPIView):
    serializer_class = KitItemAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
    # Unpaginated on purpose. The item list is not a browsable table — it is the
    # body of an editor, which must show every item. With the project-wide
    # PAGE_SIZE of 12 the Bratabandha kit (14 items) would silently lose two, and
    # an admin would have no way to tell.
    pagination_class = None

    def get_queryset(self):
        kit_id = self.kwargs.get('kit_id')
        return KitItem.objects.filter(kit_id=kit_id).select_related('product')


class AdminKitItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    """One kit item: read, change quantity or required flag, or remove.

    Was delete-only. An editor that can only add and remove forces an admin to
    delete and re-create an item just to change its quantity from 1 to 2, which
    also churns the row's id.
    """

    queryset = KitItem.objects.all()
    serializer_class = KitItemAdminSerializer
    permission_classes = [IsManagerOrReadOnly]


# --- Admin: rituals ---------------------------------------------------------
#
# Puja and PujaItem had public read endpoints but no write path, so the only way
# to edit a ritual was Django admin at /admin/. These mirror the kit views above
# exactly — same permission class, same URL shape — so the dashboard can treat a
# ritual and a kit identically.


class AdminPujaListCreateView(generics.ListCreateAPIView):
    queryset = Puja.objects.all()
    serializer_class = PujaAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
    pagination_class = None


class AdminPujaDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Puja.objects.all()
    serializer_class = PujaAdminSerializer
    permission_classes = [IsManagerOrReadOnly]


class AdminPujaItemListCreateView(generics.ListCreateAPIView):
    serializer_class = PujaItemAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
    # Unpaginated for the same reason as the kit items above: Daily Puja has 21
    # items and PAGE_SIZE is 12.
    pagination_class = None

    def get_queryset(self):
        puja_id = self.kwargs.get('puja_id')
        return PujaItem.objects.filter(puja_id=puja_id).select_related('product')


class AdminPujaItemDetailView(generics.RetrieveUpdateDestroyAPIView):
    """One ritual item — same reasoning as `AdminKitItemDetailView`."""

    queryset = PujaItem.objects.all()
    serializer_class = PujaItemAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
