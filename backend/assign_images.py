import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from products.models import Product

# Update all products to use the generic product image we generated
Product.objects.update(image='products/puja_product_generic.png')
print("Successfully mapped generated generic image to all products.")
