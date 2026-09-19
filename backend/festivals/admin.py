from django.contrib import admin
from .models import FestivalKit, KitItem, UpcomingFestival, Puja, PujaItem


class KitItemInline(admin.TabularInline):
    model = KitItem
    extra = 1


@admin.register(FestivalKit)
class FestivalKitAdmin(admin.ModelAdmin):
    list_display = ['name', 'festival_type', 'puja', 'discount_percent', 'is_active']
    list_filter = ['festival_type', 'is_active']
    inlines = [KitItemInline]


@admin.register(UpcomingFestival)
class UpcomingFestivalAdmin(admin.ModelAdmin):
    list_display = ['name', 'festival_type', 'date', 'is_active']
    list_filter = ['festival_type', 'is_active']


class PujaItemInline(admin.TabularInline):
    model = PujaItem
    extra = 1
    autocomplete_fields = ['product']


@admin.register(Puja)
class PujaAdmin(admin.ModelAdmin):
    """The ritual entry point.

    ``slug`` is read-only because ``Puja.save()`` derives it and uniquifies it —
    editing it by hand would let two rituals collide on a UNIQUE column and
    surface as an unhandled IntegrityError.
    """

    list_display = ['name', 'occasion_type', 'is_active', 'created_at']
    list_filter = ['occasion_type', 'is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {}
    readonly_fields = ['slug', 'created_at']
    inlines = [PujaItemInline]


@admin.register(PujaItem)
class PujaItemAdmin(admin.ModelAdmin):
    list_display = ['puja', 'product', 'quantity', 'is_required']
    list_filter = ['is_required', 'puja']
    autocomplete_fields = ['product']
