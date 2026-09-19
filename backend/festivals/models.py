from django.db import models
from products.models import Product

FESTIVAL_CHOICES = [
    ('dashain', 'Dashain'),
    ('tihar', 'Tihar'),
    ('shivaratri', 'Maha Shivaratri'),
    ('bratabandha', 'Bratabandha'),
    ('pasni', 'Pasni (Rice Feeding)'),
    ('griha_pravesh', 'Griha Pravesh'),
    ('shraddha', 'Shraddha'),
    ('teej', 'Teej'),
    ('chhath', 'Chhath Puja'),
    ('saraswati', 'Saraswati Puja'),
    ('nag_panchami', 'Nag Panchami'),
    ('janai_purnima', 'Janai Purnima'),
    ('other', 'Other'),
]


class FestivalKit(models.Model):
    name = models.CharField(max_length=200)
    festival_type = models.CharField(max_length=30, choices=FESTIVAL_CHOICES)
    description = models.TextField()
    image = models.ImageField(upload_to='kits/', blank=True, null=True)
    discount_percent = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['festival_type', 'name']

    @property
    def total_price(self):
        total = sum(item.product.price * item.quantity for item in self.items.select_related('product'))
        if self.discount_percent > 0:
            total = total * (100 - self.discount_percent) / 100
        return round(total, 2)

    @property
    def original_price(self):
        return sum(item.product.price * item.quantity for item in self.items.select_related('product'))

    def __str__(self):
        return f"{self.name} ({self.get_festival_type_display()})"


class KitItem(models.Model):
    kit = models.ForeignKey(FestivalKit, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    is_required = models.BooleanField(default=True)

    class Meta:
        unique_together = ('kit', 'product')

    def __str__(self):
        req = "Required" if self.is_required else "Optional"
        return f"{self.product.name} x{self.quantity} ({req})"


class UpcomingFestival(models.Model):
    """Track upcoming festivals with dates for smart predictions"""
    name = models.CharField(max_length=100)
    festival_type = models.CharField(max_length=30, choices=FESTIVAL_CHOICES)
    date = models.DateField()
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.name} - {self.date}"
