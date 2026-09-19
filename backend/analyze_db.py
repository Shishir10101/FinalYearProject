import django
import os
import sys

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from accounts.models import UserProfile
from products.models import Category, Product
from orders.models import Order, OrderItem, Cart
from festivals.models import FestivalKit, KitItem, UpcomingFestival

# Analyze database structure and content
def analyze_database():
    print("=== Puja Samagri E-Commerce Platform Database Analysis ===\n")
    
    # Get all models and their fields
    models_analysis = []
    
    # 1. Users and UserProfiles
    print("1. Analyzing Users and UserProfiles...")
    user_count = User.objects.count()
    profile_count = UserProfile.objects.count()
    
    users_without_profiles = User.objects.filter(profile__isnull=True).count()
    profiles_without_users = UserProfile.objects.filter(user__isnull=True).count()
    
    models_analysis.append({
        'table': 'Users',
        'record_count': user_count,
        'status': 'working' if user_count > 0 else 'missing data',
        'issues': f"Users without profiles: {users_without_profiles}" if users_without_profiles > 0 else "None"
    })
    
    models_analysis.append({
        'table': 'UserProfiles',
        'record_count': profile_count,
        'status': 'working' if profile_count > 0 else 'missing data',
        'issues': f"Profiles without users: {profiles_without_users}" if profiles_without_users > 0 else "None"
    })
    
    # 2. Categories
    print("2. Analyzing Categories...")
    category_count = Category.objects.count()
    empty_categories = Category.objects.filter(name='').count()
    
    models_analysis.append({
        'table': 'Categories',
        'record_count': category_count,
        'status': 'working' if category_count > 0 else 'missing data',
        'issues': f"Empty category names: {empty_categories}" if empty_categories > 0 else "None"
    })
    
    # 3. Products
    print("3. Analyzing Products...")
    product_count = Product.objects.count()
    inactive_products = Product.objects.filter(is_active=False).count()
    out_of_stock = Product.objects.filter(stock=0).count()
    
    models_analysis.append({
        'table': 'Products',
        'record_count': product_count,
        'status': 'working' if product_count > 0 else 'missing data',
        'issues': f"Inactive products: {inactive_products}, Out of stock: {out_of_stock}"
    })
    
    # 4. Orders
    print("4. Analyzing Orders...")
    order_count = Order.objects.count()
    pending_orders = Order.objects.filter(status='pending').count()
    cancelled_orders = Order.objects.filter(status='cancelled').count()
    
    models_analysis.append({
        'table': 'Orders',
        'record_count': order_count,
        'status': 'working' if order_count > 0 else 'missing data',
        'issues': f"Pending orders: {pending_orders}, Cancelled orders: {cancelled_orders}"
    })
    
    # 5. OrderItems
    print("5. Analyzing OrderItems...")
    order_item_count = OrderItem.objects.count()
    items_with_null_product = OrderItem.objects.filter(product__isnull=True).count()
    
    models_analysis.append({
        'table': 'OrderItems',
        'record_count': order_item_count,
        'status': 'working' if order_item_count > 0 else 'missing data',
        'issues': f"Items with null product: {items_with_null_product}" if items_with_null_product > 0 else "None"
    })
    
    # 6. Cart
    print("6. Analyzing Cart...")
    cart_count = Cart.objects.count()
    carts_with_null_user = Cart.objects.filter(user__isnull=True).count()
    
    models_analysis.append({
        'table': 'Cart',
        'record_count': cart_count,
        'status': 'working' if cart_count > 0 else 'missing data',
        'issues': f"Carts with null user: {carts_with_null_user}" if carts_with_null_user > 0 else "None"
    })
    
    # 7. FestivalKits
    print("7. Analyzing FestivalKits...")
    kit_count = FestivalKit.objects.count()
    inactive_kits = FestivalKit.objects.filter(is_active=False).count()
    
    models_analysis.append({
        'table': 'FestivalKits',
        'record_count': kit_count,
        'status': 'working' if kit_count > 0 else 'missing data',
        'issues': f"Inactive kits: {inactive_kits}"
    })
    
    # 8. KitItems
    print("8. Analyzing KitItems...")
    kit_item_count = KitItem.objects.count()
    kits_items_with_null_product = KitItem.objects.filter(product__isnull=True).count()
    
    models_analysis.append({
        'table': 'KitItems',
        'record_count': kit_item_count,
        'status': 'working' if kit_item_count > 0 else 'missing data',
        'issues': f"KitItems with null product: {kits_items_with_null_product}" if kits_items_with_null_product > 0 else "None"
    })
    
    # 9. UpcomingFestivals
    print("9. Analyzing UpcomingFestivals...")
    festival_count = UpcomingFestival.objects.count()
    inactive_festivals = UpcomingFestival.objects.filter(is_active=False).count()
    
    models_analysis.append({
        'table': 'UpcomingFestivals',
        'record_count': festival_count,
        'status': 'working' if festival_count > 0 else 'missing data',
        'issues': f"Inactive festivals: {inactive_festivals}"
    })
    
    # Generate summary report
    print("\n=== DATABASE ANALYSIS SUMMARY ===\n")
    
    for analysis in models_analysis:
        table_name = analysis['table']
        record_count = analysis['record_count']
        status = analysis['status']
        issues = analysis['issues']
        
        print(f"Table: {table_name}")
        print(f"  Records: {record_count}")
        print(f"  Status: {status}")
        print(f"  Issues: {issues}")
        print()
    
    # Check relationships
    print("=== RELATIONSHIP ANALYSIS ===\n")
    
    # Check foreign key constraints
    print("1. Checking foreign key relationships...")
    
    # UserProfile -> User
    valid_relationships = []
    invalid_relationships = []
    
    # Check UserProfile-User relationship
    invalid_user_profiles = UserProfile.objects.filter(user__isnull=True).count()
    if invalid_user_profiles == 0:
        valid_relationships.append("UserProfile → User: All good")
    else:
        invalid_relationships.append(f"UserProfile → User: {invalid_user_profiles} profiles without valid users")
    
    # Check Product-Category relationship
    orphaned_products = Product.objects.filter(category__isnull=True).count()
    if orphaned_products == 0:
        valid_relationships.append("Product → Category: All good")
    else:
        invalid_relationships.append(f"Product → Category: {orphaned_products} products without valid categories")
    
    # Check Order-User relationship
    orphaned_orders = Order.objects.filter(user__isnull=True).count()
    if orphaned_orders == 0:
        valid_relationships.append("Order → User: All good")
    else:
        invalid_relationships.append(f"Order → User: {orphaned_orders} orders without valid users")
    
    # Check OrderItem-Order relationship
    orphaned_order_items = OrderItem.objects.filter(order__isnull=True).count()
    if orphaned_order_items == 0:
        valid_relationships.append("OrderItem → Order: All good")
    else:
        invalid_relationships.append(f"OrderItem → Order: {orphaned_order_items} order items without valid orders")
    
    # Check OrderItem-Product relationship
    orphaned_order_items_product = OrderItem.objects.filter(product__isnull=True).count()
    if orphaned_order_items_product == 0:
        valid_relationships.append("OrderItem → Product: All good")
    else:
        invalid_relationships.append(f"OrderItem → Product: {orphaned_order_items_product} order items with null products")
    
    # Check Cart-User relationship
    orphaned_carts = Cart.objects.filter(user__isnull=True).count()
    if orphaned_carts == 0:
        valid_relationships.append("Cart → User: All good")
    else:
        invalid_relationships.append(f"Cart → User: {orphaned_carts} carts without valid users")
    
    # Check Cart-Product relationship
    orphaned_carts_product = Cart.objects.filter(product__isnull=True).count()
    if orphaned_carts_product == 0:
        valid_relationships.append("Cart → Product: All good")
    else:
        invalid_relationships.append(f"Cart → Product: {orphaned_carts_product} carts with null products")
    
    # Check KitItem-Product relationship
    orphaned_kit_items_product = KitItem.objects.filter(product__isnull=True).count()
    if orphaned_kit_items_product == 0:
        valid_relationships.append("KitItem → Product: All good")
    else:
        invalid_relationships.append(f"KitItem → Product: {orphaned_kit_items_product} kit items with null products")
    
    # Print relationship analysis
    for relationship in valid_relationships:
        print(f"✓ {relationship}")
    
    if invalid_relationships:
        for relationship in invalid_relationships:
            print(f"✗ {relationship}")
    else:
        print("All relationships are valid.")
    
    # Data quality analysis
    print("\n=== DATA QUALITY ANALYSIS ===\n")
    
    data_quality_issues = []
    
    # Check for empty required fields
    empty_names = []
    for model_name in ['User', 'Category', 'Product', 'Order', 'FestivalKit', 'UpcomingFestival']:
        if model_name == 'User':
            count = User.objects.filter(username='').count()
        elif model_name == 'Category':
            count = Category.objects.filter(name='').count()
        elif model_name == 'Product':
            count = Product.objects.filter(name='').count()
        elif model_name == 'Order':
            count = Order.objects.filter(user__username='').count()
        elif model_name == 'FestivalKit':
            count = FestivalKit.objects.filter(name='').count()
        elif model_name == 'UpcomingFestival':
            count = UpcomingFestival.objects.filter(name='').count()
        else:
            count = 0
            
        if count > 0:
            empty_names.append(f"{model_name}: {count} empty")
    
    if empty_names:
        data_quality_issues.append("Empty required fields: " + ", ".join(empty_names))
    
    # Check for negative prices
    negative_prices = Product.objects.filter(price__lt=0).count()
    if negative_prices > 0:
        data_quality_issues.append(f"Products with negative prices: {negative_prices}")
    
    # Check for negative stock
    negative_stock = Product.objects.filter(stock__lt=0).count()
    if negative_stock > 0:
        data_quality_issues.append(f"Products with negative stock: {negative_stock}")
    
    # Check for negative quantities in order items
    negative_quantities = OrderItem.objects.filter(quantity__lt=0).count()
    if negative_quantities > 0:
        data_quality_issues.append(f"Order items with negative quantities: {negative_quantities}")
    
    # Check for negative quantities in cart items
    negative_cart_quantities = Cart.objects.filter(quantity__lt=0).count()
    if negative_cart_quantities > 0:
        data_quality_issues.append(f"Cart items with negative quantities: {negative_cart_quantities}")
    
    # Check for negative quantities in kit items
    negative_kit_quantities = KitItem.objects.filter(quantity__lt=0).count()
    if negative_kit_quantities > 0:
        data_quality_issues.append(f"Kit items with negative quantities: {negative_kit_quantities}")
    
    if data_quality_issues:
        for issue in data_quality_issues:
            print(f"⚠ {issue}")
    else:
        print("No significant data quality issues found.")
    
    return models_analysis

if __name__ == '__main__':
    analyze_database()