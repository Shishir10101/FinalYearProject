from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone
from datetime import timedelta
from .models import FestivalKit, KitItem, UpcomingFestival
from products.models import Product
from .serializers import (
    FestivalKitListSerializer, FestivalKitDetailSerializer,
    UpcomingFestivalSerializer, FestivalKitAdminSerializer,
    KitItemAdminSerializer
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
    serializer_class = UpcomingFestivalSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None

    def get_queryset(self):
        today = timezone.now().date()
        return UpcomingFestival.objects.filter(
            date__gte=today,
            is_active=True
        )[:5]


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

    def get_queryset(self):
        kit_id = self.kwargs.get('kit_id')
        return KitItem.objects.filter(kit_id=kit_id)


class AdminKitItemDeleteView(generics.DestroyAPIView):
    queryset = KitItem.objects.all()
    serializer_class = KitItemAdminSerializer
    permission_classes = [IsManagerOrReadOnly]
