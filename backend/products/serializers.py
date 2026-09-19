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
    """Write serializer for the catalogue's category list.

    Validates that the name is unique. The model's ``save()`` suffixer (added to
    stop a duplicate name raising an unhandled ``IntegrityError``) made the API
    *accept* a second "Puja Oils & Ghee" and quietly file it as
    ``puja-oils-ghee-1``. Surviving the crash is right; silently creating a
    duplicate category is not — it splits one category into two and the
    storefront then shows both. The suffixer stays as the last-resort safety net;
    this check is what actually stops it happening.
    """

    class Meta:
        model = Category
        fields = '__all__'

    def validate_name(self, value):
        name = value.strip()
        if not name:
            raise serializers.ValidationError('Please enter a name.')

        clash = Category.objects.filter(name__iexact=name)
        if self.instance is not None:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError('A category with this name already exists.')
        return name
