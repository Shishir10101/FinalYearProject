import os
print("Current directory:", os.getcwd())
print("Files in current directory:")
for f in os.listdir('.'):
    print(f"  {f}")

# Check if we have Django setup
import sys
sys.path.insert(0, '.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
try:
    import django
    django.setup()
    print("Django setup successful")
except Exception as e:
    print(f"Django setup failed: {e}")

# Try to import models
from django.contrib.auth.models import User
print(f"Users count: {User.objects.count()}")