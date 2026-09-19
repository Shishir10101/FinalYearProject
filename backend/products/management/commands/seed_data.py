from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from accounts.models import UserProfile
from products.models import Category, Product
from festivals.models import FestivalKit, KitItem, UpcomingFestival
from orders.models import Order, OrderItem
from datetime import date, timedelta
from decimal import Decimal
import random


class Command(BaseCommand):
    help = 'Seed database with sample data for Puja Samagri Store'

    def handle(self, *args, **kwargs):
        self.stdout.write('Seeding database...')

        # Create admin user
        admin_user, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@pujasmagri.com',
                'first_name': 'Admin',
                'last_name': 'User',
                'is_staff': True,
                'is_superuser': True,
            }
        )
        if created:
            admin_user.set_password('admin123')
            admin_user.save()
            UserProfile.objects.create(user=admin_user, is_admin_user=True, city='kathmandu')
            self.stdout.write(self.style.SUCCESS('Admin user created (admin / admin123)'))

        # Create test user
        test_user, created = User.objects.get_or_create(
            username='testuser',
            defaults={
                'email': 'test@example.com',
                'first_name': 'Ram',
                'last_name': 'Sharma',
            }
        )
        if created:
            test_user.set_password('test1234')
            test_user.save()
            UserProfile.objects.create(
                user=test_user, phone='9841000000',
                address='Asan, Kathmandu', city='kathmandu'
            )
            self.stdout.write(self.style.SUCCESS('Test user created (testuser / test1234)'))

        # Categories
        categories_data = [
            {'name': 'Dhoop & Agarbatti', 'description': 'Incense sticks, dhoop, and fragrance items for puja'},
            {'name': 'Puja Flowers & Garlands', 'description': 'Fresh and artificial flowers, mala, and garlands'},
            {'name': 'Tika & Sindoor', 'description': 'Vermillion, tika, abir, and other tika items'},
            {'name': 'Puja Vessels', 'description': 'Kalash, plates, diyo, and other metal items'},
            {'name': 'Offerings & Prasad', 'description': 'Fruits, sweets, and prasad items'},
            {'name': 'Sacred Threads', 'description': 'Janai, kalava, mauli, and sacred threads'},
            {'name': 'Puja Oils & Ghee', 'description': 'Mustard oil, ghee, and oil for diyo'},
            {'name': 'Hawan Samagri', 'description': 'Hawan items, samagri mix, and fire ritual supplies'},
            {'name': 'Holy Books & Accessories', 'description': 'Religious books, bells, conch shells'},
            {'name': 'Festival Special', 'description': 'Special items for specific festivals'},
        ]

        categories = {}
        for cat_data in categories_data:
            cat, _ = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )
            categories[cat.name] = cat

        self.stdout.write(f'Created {len(categories)} categories')

        # Products
        products_data = [
            # Dhoop & Agarbatti
            {'name': 'Premium Dhoop Batti (Pack of 20)', 'price': 120, 'stock': 200, 'category': 'Dhoop & Agarbatti', 'is_featured': True, 'popularity_score': 85, 'unit': 'packet', 'description': 'Premium quality dhoop batti made from natural ingredients. Long-lasting fragrance perfect for daily puja.'},
            {'name': 'Chandan Agarbatti', 'price': 80, 'stock': 150, 'category': 'Dhoop & Agarbatti', 'popularity_score': 70, 'unit': 'packet', 'description': 'Pure sandalwood incense sticks with traditional fragrance.'},
            {'name': 'Camphor (Kapur) - 50g', 'price': 60, 'stock': 300, 'category': 'Dhoop & Agarbatti', 'popularity_score': 90, 'unit': 'packet', 'description': 'Pure edible camphor tablets for aarti and puja rituals.'},
            {'name': 'Loban Dhoop', 'price': 100, 'stock': 120, 'category': 'Dhoop & Agarbatti', 'popularity_score': 55, 'unit': 'packet', 'description': 'Traditional loban dhoop for smoke purification during puja.'},

            # Tika & Sindoor
            {'name': 'Sindoor Powder (Red)', 'price': 50, 'stock': 250, 'category': 'Tika & Sindoor', 'is_featured': True, 'popularity_score': 95, 'unit': 'packet', 'description': 'Pure vermillion powder for tika and religious ceremonies.'},
            {'name': 'Abir Powder (Set of 5 colors)', 'price': 150, 'stock': 100, 'category': 'Tika & Sindoor', 'popularity_score': 60, 'unit': 'set', 'description': 'Colorful abir powder set for tika during festivals.'},
            {'name': 'Chandan Tika Paste', 'price': 90, 'stock': 80, 'category': 'Tika & Sindoor', 'popularity_score': 45, 'unit': 'tube', 'description': 'Ready-to-use sandalwood paste for tika application.'},
            {'name': 'Kumkum Powder', 'price': 40, 'stock': 200, 'category': 'Tika & Sindoor', 'popularity_score': 75, 'unit': 'packet', 'description': 'Traditional kumkum powder for daily puja and special occasions.'},

            # Puja Vessels
            {'name': 'Brass Puja Kalash', 'price': 850, 'stock': 30, 'category': 'Puja Vessels', 'is_featured': True, 'popularity_score': 70, 'unit': 'piece', 'description': 'Traditional brass kalash for puja ceremonies. Beautifully crafted with traditional design.'},
            {'name': 'Copper Puja Plate (Thali)', 'price': 450, 'stock': 50, 'category': 'Puja Vessels', 'popularity_score': 65, 'unit': 'piece', 'description': 'Handmade copper puja thali for aarti and offerings.'},
            {'name': 'Brass Diyo (Oil Lamp)', 'price': 250, 'stock': 100, 'category': 'Puja Vessels', 'popularity_score': 80, 'unit': 'piece', 'description': 'Traditional brass diyo for lighting during puja.'},
            {'name': 'Achamani Set (Spoon & Cup)', 'price': 180, 'stock': 40, 'category': 'Puja Vessels', 'popularity_score': 35, 'unit': 'set', 'description': 'Copper achamani set for water offerings during puja rituals.'},
            {'name': 'Silver Coated Puja Bell', 'price': 350, 'stock': 45, 'category': 'Puja Vessels', 'popularity_score': 55, 'unit': 'piece', 'description': 'Beautiful silver-coated brass bell for puja ceremonies.'},

            # Puja Flowers & Garlands
            {'name': 'Artificial Marigold Garland', 'price': 200, 'stock': 80, 'category': 'Puja Flowers & Garlands', 'is_featured': True, 'popularity_score': 60, 'unit': 'piece', 'description': 'Beautiful artificial marigold garland that looks fresh. Reusable and long-lasting.'},
            {'name': 'Dried Rose Petals (100g)', 'price': 120, 'stock': 60, 'category': 'Puja Flowers & Garlands', 'popularity_score': 40, 'unit': 'packet', 'description': 'Dried rose petals for puja offerings and decoration.'},
            {'name': 'Cotton Wicks (Batti) - 100pcs', 'price': 30, 'stock': 500, 'category': 'Puja Flowers & Garlands', 'popularity_score': 92, 'unit': 'packet', 'description': 'Ready-made cotton wicks for diyo. Essential for every puja.'},

            # Offerings & Prasad
            {'name': 'Puja Naivedya Set', 'price': 350, 'stock': 40, 'category': 'Offerings & Prasad', 'popularity_score': 50, 'unit': 'set', 'description': 'Complete naivedya set with dry fruits, batasha, and prasad items.'},
            {'name': 'Batasha (Sugar Drops) - 250g', 'price': 80, 'stock': 200, 'category': 'Offerings & Prasad', 'popularity_score': 65, 'unit': 'packet', 'description': 'Sweet sugar drops used as offering during puja.'},
            {'name': 'Dried Coconut (Nariwal)', 'price': 60, 'stock': 150, 'category': 'Offerings & Prasad', 'popularity_score': 70, 'unit': 'piece', 'description': 'Dried coconut for puja offering. Must-have for most rituals.'},
            {'name': 'Supari (Betel Nut) Pack', 'price': 45, 'stock': 180, 'category': 'Offerings & Prasad', 'popularity_score': 72, 'unit': 'packet', 'description': 'Whole betel nuts for puja and ritual offerings.'},

            # Sacred Threads
            {'name': 'Janai (Sacred Thread)', 'price': 50, 'stock': 300, 'category': 'Sacred Threads', 'popularity_score': 88, 'unit': 'piece', 'description': 'Traditional sacred thread for Janai Purnima and Bratabandha.'},
            {'name': 'Kalava (Red Thread Roll)', 'price': 25, 'stock': 400, 'category': 'Sacred Threads', 'popularity_score': 82, 'unit': 'roll', 'description': 'Red sacred thread used for tying during puja rituals.'},
            {'name': 'Mauli Thread (Bundle)', 'price': 35, 'stock': 250, 'category': 'Sacred Threads', 'popularity_score': 60, 'unit': 'bundle', 'description': 'Sacred mauli thread for various Hindu ceremonies.'},

            # Puja Oils & Ghee
            {'name': 'Pure Cow Ghee (250ml)', 'price': 320, 'stock': 80, 'category': 'Puja Oils & Ghee', 'is_featured': True, 'popularity_score': 78, 'unit': 'bottle', 'description': 'Pure cow ghee for diyo, hawan, and puja purposes.'},
            {'name': 'Mustard Oil for Diyo (500ml)', 'price': 180, 'stock': 120, 'category': 'Puja Oils & Ghee', 'popularity_score': 85, 'unit': 'bottle', 'description': 'Traditional mustard oil specifically for lighting diyo.'},
            {'name': 'Sesame Oil (Til Oil) 250ml', 'price': 220, 'stock': 60, 'category': 'Puja Oils & Ghee', 'popularity_score': 45, 'unit': 'bottle', 'description': 'Pure sesame oil for special puja rituals and Shraddha.'},

            # Hawan Samagri
            {'name': 'Hawan Samagri Mix (500g)', 'price': 250, 'stock': 100, 'category': 'Hawan Samagri', 'is_featured': True, 'popularity_score': 72, 'unit': 'packet', 'description': 'Premium mix of herbs and ingredients for hawan fire rituals.'},
            {'name': 'Dried Mango Wood (Aam Ki Lakdi)', 'price': 150, 'stock': 70, 'category': 'Hawan Samagri', 'popularity_score': 55, 'unit': 'bundle', 'description': 'Dried mango wood sticks for hawan fire.'},
            {'name': 'Hawan Kund (Small)', 'price': 650, 'stock': 25, 'category': 'Hawan Samagri', 'popularity_score': 40, 'unit': 'piece', 'description': 'Copper hawan kund for performing fire rituals at home.'},

            # Holy Books & Accessories  
            {'name': 'Puja Bell (Ghanti)', 'price': 280, 'stock': 60, 'category': 'Holy Books & Accessories', 'popularity_score': 65, 'unit': 'piece', 'description': 'Brass puja bell with clear sound for aarti and puja.'},
            {'name': 'Conch Shell (Shankha)', 'price': 450, 'stock': 35, 'category': 'Holy Books & Accessories', 'is_featured': True, 'popularity_score': 58, 'unit': 'piece', 'description': 'Natural conch shell for blowing during puja ceremonies.'},
            {'name': 'Rudraksha Mala', 'price': 500, 'stock': 40, 'category': 'Holy Books & Accessories', 'popularity_score': 50, 'unit': 'piece', 'description': '108 bead genuine Rudraksha mala for prayer and meditation.'},

            # Festival Special
            {'name': 'Dashain Tika Set', 'price': 180, 'stock': 150, 'category': 'Festival Special', 'is_featured': True, 'popularity_score': 98, 'unit': 'set', 'description': 'Complete tika set for Dashain with sindoor, rice, and jamara seeds.'},
            {'name': 'Tihar Diyo Set (5 piece)', 'price': 350, 'stock': 100, 'category': 'Festival Special', 'popularity_score': 95, 'unit': 'set', 'description': 'Beautiful 5-piece diyo set for Tihar Laxmi Puja celebration.'},
            {'name': 'Shivaratri Puja Set', 'price': 450, 'stock': 60, 'category': 'Festival Special', 'popularity_score': 80, 'unit': 'set', 'description': 'Complete Shivaratri puja set with bel patra, dhatura, and essentials.'},
        ]

        products = {}
        for p_data in products_data:
            cat = categories[p_data.pop('category')]
            product, _ = Product.objects.get_or_create(
                name=p_data['name'],
                defaults={**p_data, 'category': cat}
            )
            products[product.name] = product

        self.stdout.write(f'Created {len(products)} products')

        # Festival Kits
        kits_data = [
            {
                'name': 'Dashain Puja Complete Kit',
                'festival_type': 'dashain',
                'description': 'Everything you need for Dashain puja — tika, garlands, diyo, and offerings. Perfect for the 10-day celebration.',
                'discount_percent': 10,
                'items': [
                    ('Dashain Tika Set', 1, True),
                    ('Sindoor Powder (Red)', 2, True),
                    ('Artificial Marigold Garland', 2, True),
                    ('Brass Diyo (Oil Lamp)', 1, True),
                    ('Premium Dhoop Batti (Pack of 20)', 1, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Mustard Oil for Diyo (500ml)', 1, True),
                    ('Dried Coconut (Nariwal)', 2, False),
                    ('Batasha (Sugar Drops) - 250g', 1, False),
                ]
            },
            {
                'name': 'Tihar Laxmi Puja Kit',
                'festival_type': 'tihar',
                'description': 'Complete kit for Laxmi Puja during Tihar. Includes all essential items for a beautiful celebration.',
                'discount_percent': 10,
                'items': [
                    ('Tihar Diyo Set (5 piece)', 1, True),
                    ('Artificial Marigold Garland', 3, True),
                    ('Premium Dhoop Batti (Pack of 20)', 2, True),
                    ('Camphor (Kapur) - 50g', 1, True),
                    ('Cotton Wicks (Batti) - 100pcs', 2, True),
                    ('Mustard Oil for Diyo (500ml)', 1, True),
                    ('Sindoor Powder (Red)', 1, True),
                    ('Abir Powder (Set of 5 colors)', 1, False),
                    ('Batasha (Sugar Drops) - 250g', 1, False),
                ]
            },
            {
                'name': 'Maha Shivaratri Puja Kit',
                'festival_type': 'shivaratri',
                'description': 'Essential items for Maha Shivaratri puja — dhatura, bel patra, and other Shiva puja items.',
                'discount_percent': 8,
                'items': [
                    ('Shivaratri Puja Set', 1, True),
                    ('Premium Dhoop Batti (Pack of 20)', 1, True),
                    ('Camphor (Kapur) - 50g', 1, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Rudraksha Mala', 1, False),
                    ('Dried Coconut (Nariwal)', 1, False),
                ]
            },
            {
                'name': 'Bratabandha Ceremony Kit',
                'festival_type': 'bratabandha',
                'description': 'Complete set for Bratabandha (Sacred Thread ceremony). Contains all traditional items needed.',
                'discount_percent': 12,
                'items': [
                    ('Janai (Sacred Thread)', 3, True),
                    ('Hawan Samagri Mix (500g)', 2, True),
                    ('Hawan Kund (Small)', 1, True),
                    ('Dried Mango Wood (Aam Ki Lakdi)', 2, True),
                    ('Pure Cow Ghee (250ml)', 1, True),
                    ('Brass Puja Kalash', 1, True),
                    ('Copper Puja Plate (Thali)', 1, True),
                    ('Sindoor Powder (Red)', 1, True),
                    ('Camphor (Kapur) - 50g', 1, True),
                    ('Dried Coconut (Nariwal)', 5, True),
                    ('Supari (Betel Nut) Pack', 2, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Conch Shell (Shankha)', 1, False),
                    ('Puja Bell (Ghanti)', 1, False),
                ]
            },
            {
                'name': 'Pasni (Rice Feeding) Kit',
                'festival_type': 'pasni',
                'description': 'Traditional items for the Pasni rice feeding ceremony for babies.',
                'discount_percent': 10,
                'items': [
                    ('Sindoor Powder (Red)', 1, True),
                    ('Copper Puja Plate (Thali)', 1, True),
                    ('Brass Diyo (Oil Lamp)', 1, True),
                    ('Premium Dhoop Batti (Pack of 20)', 1, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Kalava (Red Thread Roll)', 1, True),
                    ('Dried Coconut (Nariwal)', 1, True),
                    ('Supari (Betel Nut) Pack', 1, False),
                    ('Abir Powder (Set of 5 colors)', 1, False),
                ]
            },
            {
                'name': 'Griha Pravesh Kit',
                'festival_type': 'griha_pravesh',
                'description': 'Housewarming ceremony essentials. Bring auspiciousness to your new home.',
                'discount_percent': 10,
                'items': [
                    ('Brass Puja Kalash', 1, True),
                    ('Hawan Samagri Mix (500g)', 1, True),
                    ('Hawan Kund (Small)', 1, True),
                    ('Pure Cow Ghee (250ml)', 1, True),
                    ('Dried Mango Wood (Aam Ki Lakdi)', 1, True),
                    ('Sindoor Powder (Red)', 1, True),
                    ('Camphor (Kapur) - 50g', 1, True),
                    ('Artificial Marigold Garland', 2, True),
                    ('Premium Dhoop Batti (Pack of 20)', 2, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Brass Diyo (Oil Lamp)', 2, True),
                    ('Dried Coconut (Nariwal)', 3, True),
                    ('Conch Shell (Shankha)', 1, False),
                ]
            },
            {
                'name': 'Shraddha Ceremony Kit',
                'festival_type': 'shraddha',
                'description': 'All items needed for performing Shraddha (ancestor remembrance) rituals.',
                'discount_percent': 8,
                'items': [
                    ('Sesame Oil (Til Oil) 250ml', 1, True),
                    ('Kalava (Red Thread Roll)', 1, True),
                    ('Sindoor Powder (Red)', 1, True),
                    ('Brass Diyo (Oil Lamp)', 1, True),
                    ('Cotton Wicks (Batti) - 100pcs', 1, True),
                    ('Premium Dhoop Batti (Pack of 20)', 1, True),
                    ('Dried Coconut (Nariwal)', 1, True),
                    ('Supari (Betel Nut) Pack', 1, True),
                ]
            },
        ]

        for kit_data in kits_data:
            items_list = kit_data.pop('items')
            kit, created = FestivalKit.objects.get_or_create(
                name=kit_data['name'],
                defaults=kit_data
            )
            if created:
                for prod_name, qty, required in items_list:
                    if prod_name in products:
                        KitItem.objects.create(
                            kit=kit,
                            product=products[prod_name],
                            quantity=qty,
                            is_required=required
                        )

        self.stdout.write(f'Created {len(kits_data)} festival kits')

        # Upcoming Festivals
        today = date.today()
        festivals_upcoming = [
            {'name': 'Maha Shivaratri 2026', 'festival_type': 'shivaratri', 'date': today + timedelta(days=15), 'description': 'The great night of Lord Shiva'},
            {'name': 'Dashain 2026', 'festival_type': 'dashain', 'date': today + timedelta(days=60), 'description': 'The biggest festival of Nepal'},
            {'name': 'Tihar 2026', 'festival_type': 'tihar', 'date': today + timedelta(days=75), 'description': 'Festival of lights'},
            {'name': 'Teej 2026', 'festival_type': 'teej', 'date': today + timedelta(days=45), 'description': 'Festival for women'},
            {'name': 'Nag Panchami 2026', 'festival_type': 'nag_panchami', 'date': today + timedelta(days=30), 'description': 'Worship of serpent gods'},
        ]

        for f_data in festivals_upcoming:
            UpcomingFestival.objects.get_or_create(
                name=f_data['name'],
                defaults=f_data
            )

        self.stdout.write(self.style.SUCCESS(f'Created upcoming festivals'))

        # Create sample orders
        if not Order.objects.exists():
            sample_products = list(Product.objects.all()[:5])
            for i in range(8):
                order_date = timezone.now() - timedelta(days=random.randint(1, 30))
                statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered']
                order = Order.objects.create(
                    user=test_user,
                    total_amount=0,
                    status=random.choice(statuses),
                    payment_method=random.choice(['cod', 'esewa', 'khalti']),
                    payment_status='paid' if random.random() > 0.3 else 'pending',
                    shipping_address=f'Street {i+1}, Asan Tole',
                    shipping_city='kathmandu',
                    phone='9841000000',
                )
                order.created_at = order_date
                total = Decimal('0')
                for _ in range(random.randint(1, 4)):
                    prod = random.choice(sample_products)
                    qty = random.randint(1, 3)
                    OrderItem.objects.create(
                        order=order,
                        product=prod,
                        product_name=prod.name,
                        quantity=qty,
                        price=prod.price,
                    )
                    total += prod.price * qty
                order.total_amount = total
                order.save()

            self.stdout.write(self.style.SUCCESS('Created sample orders'))

        self.stdout.write(self.style.SUCCESS('Database seeded successfully!'))


# Need to import timezone
from django.utils import timezone
