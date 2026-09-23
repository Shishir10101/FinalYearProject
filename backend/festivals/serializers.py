from rest_framework import serializers
from .models import FestivalKit, KitItem, UpcomingFestival, Puja, PujaItem
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


class PujaItemSerializer(serializers.ModelSerializer):
    product_detail = ProductListSerializer(source='product', read_only=True)

    class Meta:
        model = PujaItem
        fields = ['id', 'product', 'product_detail', 'quantity', 'is_required']


class PujaListSerializer(serializers.ModelSerializer):
    """Compact ritual representation for the browse grid.

    ``item_count`` and ``required_count`` are read from **queryset annotations**,
    not counted per row — a SerializerMethodField here would issue two queries per
    puja on a list endpoint.
    """

    occasion_display = serializers.CharField(source='get_occasion_type_display', read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    required_count = serializers.IntegerField(read_only=True)
    kit_id = serializers.SerializerMethodField()
    kit_name = serializers.SerializerMethodField()

    class Meta:
        model = Puja
        fields = ['id', 'name', 'slug', 'description', 'occasion_type',
                  'occasion_display', 'item_count', 'required_count',
                  'kit_id', 'kit_name']

    def get_kit_id(self, obj):
        kit = obj.kit
        return kit.id if kit else None

    def get_kit_name(self, obj):
        kit = obj.kit
        return kit.name if kit else None


class PujaDetailSerializer(serializers.ModelSerializer):
    items = PujaItemSerializer(many=True, read_only=True)
    occasion_display = serializers.CharField(source='get_occasion_type_display', read_only=True)
    kit = serializers.SerializerMethodField()

    class Meta:
        model = Puja
        fields = ['id', 'name', 'slug', 'description', 'occasion_type',
                  'occasion_display', 'items', 'kit']

    def get_kit(self, obj):
        kit = obj.kit
        if kit is None:
            return None
        return FestivalKitListSerializer(kit).data


class FestivalKitAdminSerializer(serializers.ModelSerializer):
    """Write serializer for kits.

    An explicit field list rather than ``__all__``: the dashboard table needs
    ``item_count`` (a declared field is not reliably picked up by ``__all__``).

    ``image`` is now included. It was previously left out on the grounds that "a file
    upload a JSON form cannot set" — true at the time, and it meant the seeded kit
    artwork was the only artwork a kit could ever have. The dashboard now uploads
    multipart (`ImageField` + `api.upload()`), so the reason no longer holds and the
    omission would just be a column nobody can fill. It stays optional: a kit with no
    image renders the storefront placeholder, which is the same behaviour as before
    for the seven seeded kits that do have one.
    """

    item_count = serializers.SerializerMethodField()

    class Meta:
        model = FestivalKit
        fields = ['id', 'name', 'festival_type', 'description', 'discount_percent',
                  'puja', 'is_active', 'image', 'item_count', 'created_at', 'updated_at']
        read_only_fields = ['created_at', 'updated_at']

    def get_item_count(self, obj):
        return obj.items.count()


class KitItemAdminSerializer(serializers.ModelSerializer):
    """Kit items, with the product's display fields alongside the raw id.

    The dashboard needs the name and price to render a usable list; without them
    it would have to fetch every product just to label a row.
    """

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price', max_digits=10, decimal_places=2, read_only=True
    )
    product_unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model = KitItem
        fields = '__all__'


class PujaAdminSerializer(serializers.ModelSerializer):
    """Write serializer for rituals.

    `slug` is read-only because `Puja.save()` derives and uniquifies it — letting a
    client set it would allow two rituals to collide on the UNIQUE column.

    `kit_names` is read-only and informational. The link is a FK **on the kit**
    (`FestivalKit.puja`), because a kit declares which ritual it serves and one
    ritual may legitimately have several bundles. So a ritual cannot be given a
    kit from this side, and the dashboard says so rather than offering a picker
    that would have to pick one arbitrarily.
    """

    item_count = serializers.SerializerMethodField()
    kit_count = serializers.SerializerMethodField()
    kit_names = serializers.SerializerMethodField()

    class Meta:
        model = Puja
        fields = ['id', 'name', 'slug', 'description', 'occasion_type',
                  'is_active', 'item_count', 'kit_count', 'kit_names', 'created_at']
        read_only_fields = ['slug', 'created_at']

    def get_item_count(self, obj):
        return obj.items.count()

    def get_kit_count(self, obj):
        return obj.kits.count()

    def get_kit_names(self, obj):
        return [kit.name for kit in obj.kits.all()]


class PujaItemAdminSerializer(serializers.ModelSerializer):
    """Puja items, with the product's display fields alongside the raw id.

    Same shape as `KitItemAdminSerializer` on purpose: the dashboard renders both
    through one shared item manager, so the payloads must agree.
    """

    product_name = serializers.CharField(source='product.name', read_only=True)
    product_price = serializers.DecimalField(
        source='product.price', max_digits=10, decimal_places=2, read_only=True
    )
    product_unit = serializers.CharField(source='product.unit', read_only=True)

    class Meta:
        model = PujaItem
        fields = '__all__'
