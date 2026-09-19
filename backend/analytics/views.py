from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions
from django.db.models import Sum, Count
from django.utils import timezone
from datetime import timedelta
from collections import defaultdict

from orders.models import Order, OrderItem
from products.models import Product, Category
from festivals.models import UpcomingFestival

from .forecasting import (
    SeasonalForecaster,
    build_product_forecasts,
    festival_dates_for_model,
)
from core.permissions import IsStaffRole, is_manager, vendor_for
from .models import SyntheticSalesRecord


def scoped_products(user):
    """Product queryset limited to what ``user`` is allowed to analyse.

    Managers (super admin / admin) see the whole catalogue. A vendor sees only
    their own products — the scoping lives here rather than in each view so it
    cannot be forgotten in one of them.
    """
    qs = Product.objects.all()
    if is_manager(user):
        return qs
    vendor = vendor_for(user)
    if vendor is None:
        return qs.none()
    return qs.filter(vendor=vendor)


def scoped_orders(user):
    """Order queryset limited to orders containing ``user``'s products."""
    qs = Order.objects.all()
    if is_manager(user):
        return qs
    vendor = vendor_for(user)
    if vendor is None:
        return qs.none()
    return qs.filter(items__product__vendor=vendor).distinct()


class SalesOverviewView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        today = timezone.now().date()
        last_30 = today - timedelta(days=30)
        last_7 = today - timedelta(days=7)

        orders = scoped_orders(request.user)
        products_qs = scoped_products(request.user)

        total_orders = orders.count()
        total_revenue = orders.aggregate(total=Sum('total_amount'))['total'] or 0

        orders_30d = orders.filter(created_at__date__gte=last_30)
        revenue_30d = orders_30d.aggregate(total=Sum('total_amount'))['total'] or 0

        orders_7d = orders.filter(created_at__date__gte=last_7)
        revenue_7d = orders_7d.aggregate(total=Sum('total_amount'))['total'] or 0

        # Orders by status
        status_counts = dict(
            orders.values_list('status').annotate(count=Count('id')).values_list('status', 'count')
        )

        # Daily revenue for last 30 days
        daily_data = []
        for i in range(30):
            day = today - timedelta(days=29 - i)
            day_orders = orders.filter(created_at__date=day)
            day_revenue = day_orders.aggregate(total=Sum('total_amount'))['total'] or 0
            daily_data.append({
                'date': day.isoformat(),
                'revenue': float(day_revenue),
                'orders': day_orders.count()
            })

        return Response({
            'total_orders': total_orders,
            'total_revenue': float(total_revenue),
            'revenue_30d': float(revenue_30d),
            'orders_30d': orders_30d.count(),
            'revenue_7d': float(revenue_7d),
            'orders_7d': orders_7d.count(),
            'total_products': products_qs.count(),
            'scope': 'all' if is_manager(request.user) else 'vendor',
            'status_counts': status_counts,
            'daily_data': daily_data,
        })


class TrendingProductsView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        trending = scoped_products(request.user).filter(
            is_active=True
        ).order_by('-popularity_score')[:10]
        data = [{
            'id': p.id,
            'name': p.name,
            'category': p.category.name,
            'price': float(p.price),
            'stock': p.stock,
            'popularity_score': p.popularity_score,
            'image': p.image.url if p.image else None,
        } for p in trending]

        return Response(data)


class InventoryView(APIView):
    permission_classes = [IsStaffRole]

    def get(self, request):
        products = scoped_products(request.user).filter(is_active=True)

        # Low stock products (< 10)
        low_stock = products.filter(stock__lt=10).order_by('stock')

        out_of_stock = products.filter(stock=0)

        total_products = products.count()
        total_stock = products.aggregate(total=Sum('stock'))['total'] or 0

        low_stock_data = [{
            'id': p.id,
            'name': p.name,
            'category': p.category.name,
            'stock': p.stock,
            'price': float(p.price),
        } for p in low_stock[:20]]

        return Response({
            'total_products': total_products,
            'total_stock_units': total_stock,
            'out_of_stock_count': out_of_stock.count(),
            'low_stock_count': low_stock.count(),
            'low_stock_products': low_stock_data,
        })


class PredictionAlertsView(APIView):
    """Actionable alerts for the admin dashboard.

    Combines two sources:
      * the festival calendar (things you must prepare for), and
      * the demand forecast (things the model expects to sell).
    """
    permission_classes = [IsStaffRole]

    def get(self, request):
        alerts = []
        today = timezone.now().date()
        products_scope = scoped_products(request.user).filter(is_active=True)

        # 1. Upcoming festivals needing stock
        upcoming = UpcomingFestival.objects.filter(
            date__gte=today,
            date__lte=today + timedelta(days=14),
            is_active=True
        )
        for festival in upcoming:
            days_until = (festival.date - today).days
            alerts.append({
                'type': 'festival',
                'priority': 'high' if days_until <= 7 else 'medium',
                'message': f'{festival.name} is in {days_until} days. Ensure stock is ready!',
                'date': festival.date.isoformat(),
            })

        # 2. Low stock alerts
        low_stock = products_scope.filter(stock__lt=5, stock__gt=0)
        for p in low_stock[:5]:
            alerts.append({
                'type': 'inventory',
                'priority': 'high',
                'message': f'{p.name} has only {p.stock} units left',
                'product_id': p.id,
            })

        # 3. Out of stock popular items
        out_popular = products_scope.filter(stock=0, popularity_score__gt=5)
        for p in out_popular[:5]:
            alerts.append({
                'type': 'restock',
                'priority': 'critical',
                'message': f'{p.name} is out of stock but has high demand (score: {p.popularity_score})',
                'product_id': p.id,
            })

        # 4. Forecast-driven restock risk: predicted 30-day demand exceeds stock.
        visible_ids = set(products_scope.values_list('id', flat=True))
        forecast_available = SyntheticSalesRecord.objects.filter(
            product_id__in=visible_ids
        ).exists() if visible_ids else False
        if forecast_available:
            demand = dict(
                SyntheticSalesRecord.objects.filter(
                    product_id__in=visible_ids,
                    date__gte=today - timedelta(days=120)
                ).values_list('product_id').annotate(total=Sum('units_sold'))
            )
            products = {p.id: p for p in products_scope}
            for pid, total_units in sorted(demand.items(), key=lambda kv: -kv[1])[:20]:
                product = products.get(pid)
                if product is None:
                    continue
                # Scale the 120-day history down to a 30-day expectation.
                expected_30d = total_units / 4.0
                if expected_30d > product.stock:
                    shortfall = round(expected_30d - product.stock, 1)
                    alerts.append({
                        'type': 'forecast_restock',
                        'priority': 'high' if product.stock > 0 else 'critical',
                        'message': (
                            f'Forecast expects ~{expected_30d:.0f} units of '
                            f'{product.name} in 30 days but only {product.stock} '
                            f'are in stock (shortfall ~{shortfall}).'
                        ),
                        'product_id': pid,
                        'data_source': 'synthetic',
                    })

        # 5. Trending product suggestions
        trending = products_scope.order_by('-popularity_score')[:3]
        for p in trending:
            alerts.append({
                'type': 'trending',
                'priority': 'info',
                'message': f'{p.name} is trending with popularity score {p.popularity_score}',
                'product_id': p.id,
            })

        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'info': 3}
        return Response({
            'alerts': sorted(alerts, key=lambda x: priority_order[x['priority']]),
            'total': len(alerts),
            'forecast_available': forecast_available,
            'data_source': 'synthetic' if forecast_available else 'none',
        })


class DemandForecastView(APIView):
    """Per-product demand forecast.

    **Data provenance:** the history this model is fitted on is SYNTHETIC. The
    response always carries ``data_source`` and ``is_synthetic`` so the caller
    cannot accidentally present it as real demand. See
    ``docs/AI-PREDICTION.md``.

    Query params:
      * ``horizon`` — forecast window in days (default 30, max 90)
      * ``limit``   — number of products to return (default 12, max 50)
      * ``product`` — restrict to a single product id
    """
    permission_classes = [IsStaffRole]

    def get(self, request):
        today = timezone.now().date()

        try:
            horizon = int(request.query_params.get('horizon', 30))
        except (TypeError, ValueError):
            horizon = 30
        horizon = max(1, min(horizon, 90))

        try:
            limit = int(request.query_params.get('limit', 12))
        except (TypeError, ValueError):
            limit = 12
        limit = max(1, min(limit, 50))

        product_filter = request.query_params.get('product')

        visible_ids = set(scoped_products(request.user).values_list('id', flat=True))
        queryset = SyntheticSalesRecord.objects.filter(product_id__in=visible_ids)
        if product_filter:
            try:
                product_filter = int(product_filter)
            except (TypeError, ValueError):
                return Response(
                    {'error': 'product must be an integer id'},
                    status=400,
                )
            if product_filter not in visible_ids:
                return Response(
                    {'error': 'product not found in your catalogue'},
                    status=404,
                )
            queryset = queryset.filter(product_id=product_filter)

        if not queryset.exists():
            return Response({
                'data_source': 'none',
                'is_synthetic': False,
                'message': (
                    'No sales history available to forecast from. Run '
                    '`python manage.py generate_synthetic_sales` to build the '
                    'labelled synthetic dataset.'
                ),
                'horizon_days': horizon,
                'forecasts': [],
                'aggregate': {'total_forecast_units': 0, 'products_covered': 0},
                'model': {'name': 'seasonal-trend-festival', 'version': 1},
            })

        # Build {product_id: {date: units}} without loading 14k rows into models.
        daily = defaultdict(dict)
        for pid, day, units in queryset.values_list('product_id', 'date', 'units_sold'):
            daily[pid][day] = units

        festival_dates = festival_dates_for_model(today, horizon + 60)

        forecasts = build_product_forecasts(
            daily, festival_dates, horizon_days=horizon, today=today,
        )

        products = {
            p.id: p for p in Product.objects.filter(
                id__in=[f['product_id'] for f in forecasts]
            ).select_related('category')
        }

        enriched = []
        for forecast in forecasts:
            product = products.get(forecast['product_id'])
            if product is None:
                continue
            forecast_total = forecast['forecast_total_units']
            stock = product.stock
            enriched.append({
                'product': {
                    'id': product.id,
                    'name': product.name,
                    'category': product.category.name,
                    'price': float(product.price),
                    'stock': stock,
                },
                'forecast_total_units': forecast_total,
                'avg_daily_units': forecast['avg_daily_units'],
                'stock_cover_days': (
                    round(stock / forecast['avg_daily_units'], 1)
                    if forecast['avg_daily_units'] > 0 else None
                ),
                'restock_needed': forecast_total > stock,
                'projected_shortfall': (
                    round(forecast_total - stock, 1) if forecast_total > stock else 0
                ),
                'metrics': forecast['metrics'],
                'components': forecast['components'],
                'predictions': forecast['predictions'],
            })

        # Rank by how much stock risk the forecast implies.
        enriched.sort(key=lambda e: -e['projected_shortfall'])

        total_forecast = sum(e['forecast_total_units'] for e in enriched)
        mapes = [e['metrics']['mape'] for e in enriched if e['metrics'].get('mape') is not None]

        return Response({
            'data_source': 'synthetic',
            'is_synthetic': True,
            'provenance_note': (
                'SYNTHETIC DATA: this forecast is fitted on a generated dataset, '
                'not on real customer orders. It demonstrates the forecasting '
                'pipeline and must not be presented as real demand.'
            ),
            'horizon_days': horizon,
            'generated_at': timezone.now().isoformat(),
            'forecasts': enriched[:limit],
            'aggregate': {
                'total_forecast_units': round(total_forecast, 1),
                'products_covered': len(enriched),
                'products_needing_restock': sum(1 for e in enriched if e['restock_needed']),
                'mean_mape': round(sum(mapes) / len(mapes), 2) if mapes else None,
                'mean_mape_note': (
                    'Average out-of-sample MAPE across products. Measured on a '
                    'held-out tail of the series.'
                ),
            },
            'model': {
                'name': 'seasonal-trend-festival',
                'version': 1,
                'description': (
                    'Multiplicative decomposition: level x weekday seasonality x '
                    'festival calendar ramp x damped trend.'
                ),
                'horizon_days': horizon,
            },
        })
