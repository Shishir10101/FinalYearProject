from django.urls import path
from .views import (
    FestivalKitListView, FestivalKitDetailView,
    UpcomingFestivalsView, RecommendationsView,
    AdminFestivalKitListCreateView, AdminFestivalKitDetailView,
    AdminKitItemListCreateView, AdminKitItemDeleteView
)

urlpatterns = [
    # Public
    path('kits/', FestivalKitListView.as_view(), name='kit-list'),
    path('kits/<int:pk>/', FestivalKitDetailView.as_view(), name='kit-detail'),
    path('upcoming/', UpcomingFestivalsView.as_view(), name='upcoming-festivals'),
    path('recommendations/', RecommendationsView.as_view(), name='recommendations'),
    # Admin
    path('admin/kits/', AdminFestivalKitListCreateView.as_view(), name='admin-kit-list'),
    path('admin/kits/<int:pk>/', AdminFestivalKitDetailView.as_view(), name='admin-kit-detail'),
    path('admin/kits/<int:kit_id>/items/', AdminKitItemListCreateView.as_view(), name='admin-kit-items'),
    path('admin/kit-items/<int:pk>/', AdminKitItemDeleteView.as_view(), name='admin-kit-item-delete'),
]
