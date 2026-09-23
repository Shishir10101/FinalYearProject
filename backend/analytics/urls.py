from django.urls import path
from .views import (
    SalesOverviewView, TrendingProductsView, InventoryView,
    PredictionAlertsView, DemandForecastView, AreaBreakdownView,
)

urlpatterns = [
    path('sales/', SalesOverviewView.as_view(), name='sales-overview'),
    path('trending/', TrendingProductsView.as_view(), name='trending-products'),
    path('inventory/', InventoryView.as_view(), name='inventory'),
    path('predictions/', PredictionAlertsView.as_view(), name='prediction-alerts'),
    path('demand-forecast/', DemandForecastView.as_view(), name='demand-forecast'),
    path('areas/', AreaBreakdownView.as_view(), name='area-breakdown'),
]
