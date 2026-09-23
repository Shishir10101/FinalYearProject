from django.urls import path
from .views import (
    RegisterView, ProfileView, VersionedTokenObtainPairView, VersionedTokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    LogoutAllView, AdminUserListView, PasswordChangeView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    # The versioned view, not the stock one: it stamps the token version claim that
    # makes revocation possible.
    path('login/', VersionedTokenObtainPairView.as_view(), name='token_obtain_pair'),
    # The versioned view: the stock one would keep refreshing a revoked token.
    path('token/refresh/', VersionedTokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),
    # Authenticated change, as distinct from the reset above: needs the current
    # password and does not need the mailbox.
    path('password-change/', PasswordChangeView.as_view(), name='password-change'),
    path('logout-all/', LogoutAllView.as_view(), name='logout-all'),
    # Manager-only. Backs the vendor form's account picker; see the view's docstring
    # for why reading it is restricted more tightly than the rest of the admin API.
    path('admin/users/', AdminUserListView.as_view(), name='admin-user-list'),
]
