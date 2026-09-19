from django.contrib import admin
from .models import FestivalKit, KitItem, UpcomingFestival


class KitItemInline(admin.TabularInline):
    model = KitItem
    extra = 1


@admin.register(FestivalKit)
class FestivalKitAdmin(admin.ModelAdmin):
    list_display = ['name', 'festival_type', 'discount_percent', 'is_active']
    list_filter = ['festival_type', 'is_active']
    inlines = [KitItemInline]


@admin.register(UpcomingFestival)
class UpcomingFestivalAdmin(admin.ModelAdmin):
    list_display = ['name', 'festival_type', 'date', 'is_active']
    list_filter = ['festival_type', 'is_active']
