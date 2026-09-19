"""Token versioning — how a password reset actually ends existing sessions.

**The problem.** JWTs are stateless. Once issued, an access token is valid until
it expires, and nothing the server does can change that — there is no session
record to delete. This project's access tokens last a day, so before this existed a
password reset left any stolen token working for up to 24 hours. `docs/CURRENT-STATE.md`
recorded that as a known limitation; this module removes it.

**Why not SimpleJWT's `token_blacklist` app?** That app blacklists *refresh*
tokens. It is the right tool for "this refresh token was rotated" and the wrong
tool for "log this user out everywhere", because the access token derived from a
blacklisted refresh token keeps working until its own expiry. The threat here is
precisely the outstanding access token.

**The approach.** Every token carries the user's current `token_version` as a
claim. `VersionedJWTAuthentication` compares that claim against the stored value on
every authenticated request and rejects a mismatch. Bumping `token_version`
therefore invalidates everything issued before the bump, immediately, for that user
only.

**Backwards compatibility.** Tokens minted before this existed carry no claim and
are read as version 0, which matches the default. So deploying this does not sign
anybody out — only a deliberate bump does.
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import (
    TokenObtainPairSerializer, TokenRefreshSerializer,
)
from rest_framework_simplejwt.settings import api_settings

User = get_user_model()

TOKEN_VERSION_CLAIM = 'tv'

REVOKED_MESSAGE = 'This session has ended. Please log in again.'


def token_version_for(user):
    """The user's current token version, or 0 when they have no profile.

    `getattr(user, 'profile', None)` is safe for a user without a profile:
    Django's `RelatedObjectDoesNotExist` subclasses `AttributeError`, so the
    default is returned rather than raising. That matters because a user with no
    profile is a real state in this project's history — `vendor1` spent a while
    without one — and authentication must not explode because of it.
    """
    profile = getattr(user, 'profile', None)
    return profile.token_version if profile is not None else 0


def claim_matches(user, validated_token):
    """Whether a decoded token's version claim matches the user's stored version."""
    return validated_token.get(TOKEN_VERSION_CLAIM, 0) == token_version_for(user)


@transaction.atomic
def revoke_tokens(user):
    """Invalidate every token issued to ``user`` so far.

    Returns the new version. A profile is created if the user somehow has none,
    because failing to revoke would be a security failure — and
    `QuerySet.update()` against a missing row silently matches nothing, which is
    exactly how this project once left `vendor1` with no profile at all.
    """
    from .models import UserProfile

    profile, _ = UserProfile.objects.get_or_create(user=user)
    profile.token_version += 1
    profile.save(update_fields=['token_version', 'updated_at'])
    return profile.token_version


class VersionedJWTAuthentication(JWTAuthentication):
    """JWTAuthentication that also enforces the token version claim.

    Hooking into `get_user` rather than `authenticate` keeps the standard flow
    (header parsing, signature and expiry checks, token-type check) and adds the
    one extra condition. Raising `AuthenticationFailed` here surfaces as a 401 with
    `code='token_revoked'`, which the frontends already treat as "clear the token
    and send the user to login".
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not claim_matches(user, validated_token):
            raise AuthenticationFailed(REVOKED_MESSAGE, code='token_revoked')
        return user


class VersionedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Stamps the current token version onto the tokens it issues.

    The refresh token is stamped too, and SimpleJWT copies custom claims onto the
    access token it derives from a refresh, so a rotated pair stays consistent.

    The matching *view* lives in `accounts/views.py`, not here. This module is
    imported while DRF is still initialising its settings (it provides
    `DEFAULT_AUTHENTICATION_CLASSES`), and importing `simplejwt.views` at this
    point pulls in the view machinery mid-initialisation and raises a circular
    ImportError. Serializers are safe; views are not.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token[TOKEN_VERSION_CLAIM] = token_version_for(user)
        return token


class VersionedTokenRefreshSerializer(TokenRefreshSerializer):
    """Refresh that refuses a token issued before the last revocation.

    This is not optional. The refresh endpoint does **not** go through DRF's
    authentication classes — it validates the refresh token itself — so a revoked
    user's refresh token would otherwise still be accepted and still mint new
    access tokens. Those would then be rejected on use, but the endpoint would
    answer `200`, which is both misleading and lets a holder keep trying.

    Checked here, the whole chain dies at the first step.
    """

    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user_id = refresh.get(api_settings.USER_ID_CLAIM)

        user = None
        if user_id is not None:
            user = User.objects.filter(**{api_settings.USER_ID_FIELD: user_id}).first()

        if user is None or not claim_matches(user, refresh):
            raise AuthenticationFailed(REVOKED_MESSAGE, code='token_revoked')

        return super().validate(attrs)
