from django.urls import path
from .views import (
    FestivalKitListView, FestivalKitDetailView,
    UpcomingFestivalsView, RecommendationsView,
    FestivalChoicesView,
    PujaListView, PujaDetailView,
    AdminFestivalKitListCreateView, AdminFestivalKitDetailView,
    AdminKitItemListCreateView, AdminKitItemDetailView,
    AdminPujaListCreateView, AdminPujaDetailView,
    AdminPujaItemListCreateView, AdminPujaItemDetailView,
)

urlpatterns = [
    # Public
    path('kits/', FestivalKitListView.as_view(), name='kit-list'),
    path('kits/<int:pk>/', FestivalKitDetailView.as_view(), name='kit-detail'),
    path('upcoming/', UpcomingFestivalsView.as_view(), name='upcoming-festivals'),
    path('recommendations/', RecommendationsView.as_view(), name='recommendations'),
    # The enum itself, for the dashboard's authoring forms. Literal, and placed
    # before the `pujas/<slug>/` pattern only for readability — it cannot collide
    # with anything, since every other pattern here is either a literal or nested.
    path('choices/', FestivalChoicesView.as_view(), name='festival-choices'),
    # Rituals. The literal `pujas/` must precede nothing else here — the slug
    # pattern is nested under the `pujas/` prefix, so it cannot shadow any other
    # route in this module.
    path('pujas/', PujaListView.as_view(), name='puja-list'),
    path('pujas/<slug:slug>/', PujaDetailView.as_view(), name='puja-detail'),
    # Admin
    path('admin/kits/', AdminFestivalKitListCreateView.as_view(), name='admin-kit-list'),
    path('admin/kits/<int:pk>/', AdminFestivalKitDetailView.as_view(), name='admin-kit-detail'),
    path('admin/kits/<int:kit_id>/items/', AdminKitItemListCreateView.as_view(), name='admin-kit-items'),
    path('admin/kit-items/<int:pk>/', AdminKitItemDetailView.as_view(), name='admin-kit-item-detail'),
    path('admin/pujas/', AdminPujaListCreateView.as_view(), name='admin-puja-list'),
    path('admin/pujas/<int:pk>/', AdminPujaDetailView.as_view(), name='admin-puja-detail'),
    path('admin/pujas/<int:puja_id>/items/', AdminPujaItemListCreateView.as_view(), name='admin-puja-items'),
    path('admin/puja-items/<int:pk>/', AdminPujaItemDetailView.as_view(), name='admin-puja-item-detail'),
]
