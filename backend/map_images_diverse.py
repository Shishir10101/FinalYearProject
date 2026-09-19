import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from products.models import Product, Category
from festivals.models import FestivalKit

# Map specific images based on Category
dhoop_cat = Category.objects.filter(name__icontains='Dhoop').first()
if dhoop_cat:
    Product.objects.filter(category=dhoop_cat).update(image='products/incense_dhoop.png')

flower_cat = Category.objects.filter(name__icontains='Flowers').first()
if flower_cat:
    Product.objects.filter(category=flower_cat).update(image='products/puja_marigold.png')

tika_cat = Category.objects.filter(name__icontains='Tika').first()
if tika_cat:
    Product.objects.filter(category=tika_cat).update(image='products/puja_tika.png')

# Map Festival kits to the specialized festival kit image!
FestivalKit.objects.update(image='products/festival_kit_generic.png')

print("Successfully mapped specialized premium images to diverse categories and kits!")
