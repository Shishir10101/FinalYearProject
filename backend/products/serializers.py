from rest_framework import serializers
from .models import Area, Category, Product, Review, Vendor


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
    # Read from queryset annotations, never counted per row — a SerializerMethodField
    # here would issue two queries per product on any list that uses this serializer.
    average_rating = serializers.FloatField(read_only=True, allow_null=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = ['id', 'name', 'slug', 'description', 'price', 'stock',
                  'image', 'category', 'vendor', 'is_featured', 'in_stock',
                  'popularity_score', 'unit', 'created_at',
                  'average_rating', 'review_count']


# --- Reviews ---------------------------------------------------------------


class ReviewSerializer(serializers.ModelSerializer):
    """A review as the storefront renders it.

    The reviewer's identity is deliberately reduced to a display name and whether the
    account is verified. A public review list has no business publishing usernames or
    email addresses — anyone can read it.
    """

    author = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Review
        fields = ['id', 'rating', 'title', 'body', 'author', 'is_mine',
                  'is_verified_purchase', 'created_at', 'updated_at']

    def get_author(self, obj):
        """A display name, never a full identity.

        "Ram S." rather than "Ram Sharma" or the username: this list is public, and a
        review page is not a place to publish who bought what. Falls back to the
        username when no name is set, and never to an email address.
        """
        full = f'{obj.user.first_name} {obj.user.last_name}'.strip()
        if not full:
            return obj.user.username
        parts = full.split()
        if len(parts) == 1:
            return parts[0]
        return f'{parts[0]} {parts[-1][0].upper()}.'

    def get_is_mine(self, obj):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(user and user.is_authenticated and obj.user_id == user.id)


class ReviewWriteSerializer(serializers.ModelSerializer):
    """Create or update **your own** review.

    `user` and `product` are not writable: both come from the URL and the session.
    Accepting them would let a client post a review as somebody else, or file one
    against a product it never saw.
    """

    class Meta:
        model = Review
        fields = ['rating', 'title', 'body']

    def validate_rating(self, value):
        if not 1 <= value <= 5:
            raise serializers.ValidationError('Choose a rating from 1 to 5 stars.')
        return value

    def validate(self, attrs):
        """A rating on its own is not a review.

        Applied on update as well as create: `partial` PATCHes are how a bare rating
        would otherwise be left behind after the text was cleared.
        """
        def current(field):
            if field in attrs:
                return attrs[field] or ''
            return getattr(self.instance, field, '') or '' if self.instance else ''

        if not current('body').strip() and not current('title').strip():
            raise serializers.ValidationError({
                'body': 'Please add a few words, or at least a title, so the rating means something.',
            })
        return attrs


class ReviewAdminSerializer(serializers.ModelSerializer):
    """Moderation view: who wrote it, about what, and whether it is visible."""

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_slug = serializers.CharField(source='product.slug', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)

    class Meta:
        model = Review
        fields = ['id', 'product', 'product_name', 'product_slug', 'user', 'username',
                  'rating', 'title', 'body', 'is_approved', 'is_verified_purchase',
                  'created_at', 'updated_at']
        # `is_verified_purchase` is a snapshot taken when the review was written.
        read_only_fields = ['product', 'user', 'is_verified_purchase',
                            'created_at', 'updated_at']


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
