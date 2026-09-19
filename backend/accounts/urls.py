from django.urls import path
from .views import (
    RegisterView, ProfileView, VersionedTokenObtainPairView, VersionedTokenRefreshView,
    PasswordResetRequestView, PasswordResetConfirmView,
    LogoutAllView,
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
    path('logout-all/', LogoutAllView.as_view(), name='logout-all'),
]
