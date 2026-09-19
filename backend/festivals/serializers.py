from rest_framework import serializers
from .models import FestivalKit, KitItem, UpcomingFestival
from products.serializers import ProductListSerializer


class KitItemSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source='product', read_only=True)

    class Meta:
        model = KitItem
        fields = ['id', 'product', 'product_detail', 'quantity', 'is_required']


class FestivalKitListSerializer(serializers.ModelSerializer):
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    original_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    festival_type_display = serializers.CharField(source='get_festival_type_display', read_only=True)
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = FestivalKit
        fields = ['id', 'name', 'festival_type', 'festival_type_display',
                  'description', 'image', 'discount_percent',
                  'total_price', 'original_price', 'item_count']

    def get_item_count(self, obj):
        return obj.items.count()


class FestivalKitDetailSerializer(serializers.ModelSerializer):
    items = KitItemSerializer(many=True, read_only=True)
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    original_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    festival_type_display = serializers.CharField(source='get_festival_type_display', read_only=True)

    class Meta:
        model = FestivalKit
        fields = ['id', 'name', 'festival_type', 'festival_type_display',
                  'description', 'image', 'discount_percent',
                  'total_price', 'original_price', 'items']


class UpcomingFestivalSerializer(serializers.ModelSerializer):
    festival_type_display = serializers.CharField(source='get_festival_type_display', read_only=True)

    class Meta:
        model = UpcomingFestival
        fields = ['id', 'name', 'festival_type', 'festival_type_display', 'date', 'description']


class FestivalKitAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = FestivalKit
        fields = '__all__'


class KitItemAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = KitItem
        fields = '__all__'
