from rest_framework import serializers
from .models import Area, Category, Product, Vendor


class AreaSerializer(serializers.ModelSerializer):
    vendor_count = serializers.SerializerMethodField()

    class Meta:
        model = Area
        fields = ['id', 'name', 'slug', 'district', 'delivery_fee',
                  'is_active', 'vendor_count']
        read_only_fields = ['slug']

    def get_vendor_count(self, obj):
        return obj.vendors.count()


class VendorSerializer(serializers.ModelSerializer):
    user_username = serializers.CharField(source='user.username', read_only=True)
    area_name = serializers.CharField(source='area.name', read_only=True)
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = ['id', 'user', 'user_username', 'shop_name', 'slug',
                  'description', 'phone', 'address', 'area', 'area_name',
                  'is_active', 'product_count', 'created_at']
        read_only_fields = ['slug', 'created_at']

    def get_product_count(self, obj):
        return obj.products.count()


class VendorSummarySerializer(serializers.ModelSerializer):
    """Compact vendor representation embedded in product payloads."""
    class Meta:
        model = Vendor
        fields = ['id', 'shop_name', 'slug', 'area']


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image', 'product_count']

    def get_product_count(self, obj):
        return obj.products.filter(is_active=True).count()


class ProductListSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.shop_name', read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'price', 'stock', 'image',
                  'category', 'category_name', 'vendor', 'vendor_name',
                  'is_featured', 'in_stock', 'popularity_score', 'unit']


class ProductDetailSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    vendor = VendorSummarySerializer(read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'price', 'stock',
                  'image', 'category', 'vendor', 'is_featured', 'in_stock',
                  'popularity_score', 'unit', 'created_at']


class ProductAdminSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    vendor_name = serializers.CharField(source='vendor.shop_name', read_only=True)

    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['slug', 'created_at', 'updated_at']


class CategoryAdminSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = '__all__'
