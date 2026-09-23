import os
import sys

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Import Django and setup
import django
django.setup()

# Import models
from django.contrib.auth.models import User
from accounts.models import UserProfile
from products.models import Category, Product
from orders.models import Order, OrderItem, Cart
from festivals.models import FestivalKit, KitItem, UpcomingFestival

# Run analysis
print("=== Puja Sewa E-Commerce Platform Database Analysis ===\n")

# 1. Users and UserProfiles
print("1. Users and UserProfiles:")
user_count = User.objects.count()
profile_count = UserProfile.objects.count()
print(f"   Users: {user_count}")
print(f"   UserProfiles: {profile_count}")
users_without_profiles = User.objects.filter(profile__isnull=True).count()
if users_without_profiles > 0:
    print(f"   ⚠ WARNING: {users_without_profiles} users without profiles")
else:
    print(f"   ✓ All users have profiles")
print()

# 2. Categories
print("2. Categories:")
category_count = Category.objects.count()
print(f"   Categories: {category_count}")
print(f"   Status: {'✓ Working' if category_count > 0 else '✗ Missing data'}")
print()

# 3. Products
print("3. Products:")
product_count = Product.objects.count()
print(f"   Products: {product_count}")
inactive_products = Product.objects.filter(is_active=False).count()
out_of_stock = Product.objects.filter(stock=0).count()
print(f"   Inactive products: {inactive_products}")
print(f"   Out of stock products: {out_of_stock}")
print(f"   Status: {'✓ Working' if product_count > 0 else '✗ Missing data'}")
print()

# 4. Orders
print("4. Orders:")
order_count = Order.objects.count()
print(f"   Orders: {order_count}")
pending_orders = Order.objects.filter(status='pending').count()
cancelled_orders = Order.objects.filter(status='cancelled').count()
print(f"   Pending orders: {pending_orders}")
print(f"   Cancelled orders: {cancelled_orders}")
print(f"   Status: {'✓ Working' if order_count > 0 else '✗ Missing data'}")
print()

# 5. OrderItems
print("5. OrderItems:")
order_item_count = OrderItem.objects.count()
print(f"   OrderItems: {order_item_count}")
items_with_null_product = OrderItem.objects.filter(product__isnull=True).count()
if items_with_null_product > 0:
    print(f"   ⚠ WARNING: {items_with_null_product} items with null product")
else:
    print(f"   ✓ No items with null product")
print(f"   Status: {'✓ Working' if order_item_count > 0 else '✗ Missing data'}")
print()

# 6. Cart
print("6. Cart:")
cart_count = Cart.objects.count()
print(f"   Cart items: {cart_count}")
carts_with_null_user = Cart.objects.filter(user__isnull=True).count()
if carts_with_null_user > 0:
    print(f"   ⚠ WARNING: {carts_with_null_user} carts without valid users")
else:
    print(f"   ✓ All carts have valid users")
print(f"   Status: {'✓ Working' if cart_count > 0 else '✗ Missing data'}")
print()

# 7. FestivalKits
print("7. FestivalKits:")
kit_count = FestivalKit.objects.count()
print(f"   FestivalKits: {kit_count}")
inactive_kits = FestivalKit.objects.filter(is_active=False).count()
print(f"   Inactive kits: {inactive_kits}")
print(f"   Status: {'✓ Working' if kit_count > 0 else '✗ Missing data'}")
print()

# 8. KitItems
print("8. KitItems:")
kit_item_count = KitItem.objects.count()
print(f"   KitItems: {kit_item_count}")
kits_items_with_null_product = KitItem.objects.filter(product__isnull=True).count()
if kits_items_with_null_product > 0:
    print(f"   ⚠ WARNING: {kits_items_with_null_product} kit items with null product")
else:
    print(f"   ✓ No kit items with null product")
print(f"   Status: {'✓ Working' if kit_item_count > 0 else '✗ Missing data'}")
print()

# 9. UpcomingFestivals
print("9. UpcomingFestivals:")
festival_count = UpcomingFestival.objects.count()
print(f"   UpcomingFestivals: {festival_count}")
inactive_festivals = UpcomingFestival.objects.filter(is_active=False).count()
print(f"   Inactive festivals: {inactive_festivals}")
print(f"   Status: {'✓ Working' if festival_count > 0 else '✗ Missing data'}")
print()

# Relationship Analysis
print("=== Relationship Analysis ===")
print()

print("1. Foreign Key Relationships:")

# UserProfile -> User
orphaned_user_profiles = UserProfile.objects.filter(user__isnull=True).count()
if orphaned_user_profiles == 0:
    print("   ✓ UserProfile → User: All good")
else:
    print(f"   ✗ UserProfile → User: {orphaned_user_profiles} profiles without valid users")

# Product -> Category
orphaned_products = Product.objects.filter(category__isnull=True).count()
if orphaned_products == 0:
    print("   ✓ Product → Category: All good")
else:
    print(f"   ✗ Product → Category: {orphaned_products} products without valid categories")

# Order -> User
orphaned_orders = Order.objects.filter(user__isnull=True).count()
if orphaned_orders == 0:
    print("   ✓ Order → User: All good")
else:
    print(f"   ✗ Order → User: {orphaned_orders} orders without valid users")

# OrderItem -> Order
orphaned_order_items = OrderItem.objects.filter(order__isnull=True).count()
if orphaned_order_items == 0:
    print("   ✓ OrderItem → Order: All good")
else:
    print(f"   ✗ OrderItem → Order: {orphaned_order_items} order items without valid orders")

# OrderItem -> Product
orphaned_order_items_product = OrderItem.objects.filter(product__isnull=True).count()
if orphaned_order_items_product == 0:
    print("   ✓ OrderItem → Product: All good")
else:
    print(f"   ✗ OrderItem → Product: {orphaned_order_items_product} order items with null products")

# Cart -> User
orphaned_carts = Cart.objects.filter(user__isnull=True).count()
if orphaned_carts == 0:
    print("   ✓ Cart → User: All good")
else:
    print(f"   ✗ Cart → User: {orphaned_carts} carts without valid users")

# Cart -> Product
orphaned_carts_product = Cart.objects.filter(product__isnull=True).count()
if orphaned_carts_product == 0:
    print("   ✓ Cart → Product: All good")
else:
    print(f"   ✗ Cart → Product: {orphaned_carts_product} carts with null products")

# KitItem -> Product
orphaned_kit_items_product = KitItem.objects.filter(product__isnull=True).count()
if orphaned_kit_items_product == 0:
    print("   ✓ KitItem → Product: All good")
else:
    print(f"   ✗ KitItem → Product: {orphaned_kit_items_product} kit items with null products")

print()

# Data Quality Analysis
print("=== Data Quality Analysis ===")
print()

# Check for empty required fields
print("1. Empty Required Fields:")
empty_issues = []

# Check empty usernames
empty_users = User.objects.filter(username='').count()
if empty_users > 0:
    empty_issues.append(f"Users: {empty_users} empty usernames")

# Check empty category names
empty_categories = Category.objects.filter(name='').count()
if empty_categories > 0:
    empty_issues.append(f"Categories: {empty_categories} empty names")

# Check empty product names
empty_products = Product.objects.filter(name='').count()
if empty_products > 0:
    empty_issues.append(f"Products: {empty_products} empty names")

if empty_issues:
    for issue in empty_issues:
        print(f"   ⚠ {issue}")
else:
    print("   ✓ No empty required fields found")

print()

# Check for negative values
print("2. Invalid Values:")
invalid_issues = []

# Negative prices
negative_prices = Product.objects.filter(price__lt=0).count()
if negative_prices > 0:
    invalid_issues.append(f"Products with negative prices: {negative_prices}")

# Negative stock
negative_stock = Product.objects.filter(stock__lt=0).count()
if negative_stock > 0:
    invalid_issues.append(f"Products with negative stock: {negative_stock}")

# Negative quantities in cart
negative_cart_quantities = Cart.objects.filter(quantity__lt=0).count()
if negative_cart_quantities > 0:
    invalid_issues.append(f"Cart items with negative quantities: {negative_cart_quantities}")

# Negative quantities in order items
negative_order_quantities = OrderItem.objects.filter(quantity__lt=0).count()
if negative_order_quantities > 0:
    invalid_issues.append(f"Order items with negative quantities: {negative_order_quantities}")

# Negative quantities in kit items
negative_kit_quantities = KitItem.objects.filter(quantity__lt=0).count()
if negative_kit_quantities > 0:
    invalid_issues.append(f"Kit items with negative quantities: {negative_kit_quantities}")

if invalid_issues:
    for issue in invalid_issues:
        print(f"   ⚠ {issue}")
else:
    print("   ✓ No invalid values found")

print()

# Summary
print("=== Summary ===")
models = [
    ("Users", user_count),
    ("UserProfiles", profile_count),
    ("Categories", category_count),
    ("Products", product_count),
    ("Orders", order_count),
    ("OrderItems", order_item_count),
    ("Cart", cart_count),
    ("FestivalKits", kit_count),
    ("KitItems", kit_item_count),
    ("UpcomingFestivals", festival_count)
]

print("Table\t\t\tRecords\tStatus")
print("-" * 60)
total_records = 0
for table, count in models:
    status = "✓ Working" if count > 0 else "✗ Missing data"
    print(f"{table:<20}\t{count:<8}\t{status}")
    total_records += count

print("-" * 60)
print(f"{"-" * 60}")
print(f"Grand Total Records: {total_records}")
print(f"✅ Database analysis complete!")