from django.db import models
from django.contrib.auth.models import User

from core.constants import CITY_CHOICES
from core.permissions import ROLE_CUSTOMER, ROLE_CHOICES


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=15, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=20, choices=CITY_CHOICES, default='kathmandu')

    # The authoritative role. Read by ``core.permissions.get_role``.
    #
    # ``is_admin_user`` below is kept for backwards compatibility with existing
    # rows and the Django admin, but it is no longer the source of truth: a
    # boolean could not express four roles, and it was never actually enforced.
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER,
        help_text='Authorization role. Super Admin > Admin > Vendor > Customer.',
    )
    is_admin_user = models.BooleanField(
        default=False,
        help_text='Legacy flag, superseded by `role`. Kept so existing data is not lost.',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['role'])]

    def save(self, *args, **kwargs):
        # Keep the legacy flag consistent so the Django admin filter stays useful
        # and any code we have not yet migrated still behaves sensibly.
        if self.role in ('super_admin', 'admin'):
            self.is_admin_user = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username}'s profile ({self.role})"
