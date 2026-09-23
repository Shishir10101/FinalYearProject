from django.contrib import admin
from .models import Category, Product, Review, WishlistItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'stock', 'is_featured', 'is_active']
    list_filter = ['category', 'is_featured', 'is_active']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'rating', 'is_approved', 'is_verified_purchase',
                    'created_at']
    list_filter = ['is_approved', 'is_verified_purchase', 'rating']
    search_fields = ['product__name', 'user__username', 'title', 'body']
    # `is_verified_purchase` is a snapshot taken when the review was written, so it
    # must not be editable here — see the model docstring.
    readonly_fields = ['is_verified_purchase', 'created_at', 'updated_at']


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ['product', 'user', 'created_at']
    list_filter = ['created_at']
    search_fields = ['product__name', 'user__username']
    readonly_fields = ['created_at']
    # No `add` in the admin: a wishlist row is written by the customer pressing the
    # heart, never by staff. This screen exists to answer "what is saved, and by
    # whom", not to author entries.
    def has_add_permission(self, request):
        return False
