"""Password-reset token helpers.

The token itself is Django's own ``default_token_generator`` rather than anything
hand-rolled. That matters, because its hash is built from the user's **current
password hash** and ``last_login``. Two properties fall out of that for free:

* a reset link stops working the moment it is used — the password hash changed,
  so the token no longer matches;
* a reset link stops working if the account owner logs in in the meantime.

A naive implementation that stored a random string in a column and deleted it
afterwards gets the first property only by remembering to do the delete, and
loses the second entirely.
"""

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode


def encode_uid(user):
    """Opaque, URL-safe user identifier. Not the raw pk."""
    return urlsafe_base64_encode(force_bytes(user.pk))


def decode_uid(uid):
    """Return the user for an encoded uid, or ``None`` if it is unusable.

    Every failure mode collapses to ``None`` on purpose: a malformed uid must be
    indistinguishable from a valid uid with a bad token, otherwise the endpoint
    becomes an oracle for which account ids exist.
    """
    from django.contrib.auth.models import User

    try:
        pk = force_str(urlsafe_base64_decode(uid))
        return User.objects.get(pk=pk)
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        return None


def make_token(user):
    return default_token_generator.make_token(user)


def check_token(user, token):
    return default_token_generator.check_token(user, token)


def build_reset_url(user):
    """Absolute link to the storefront reset page, with uid and token attached."""
    base = settings.FRONTEND_URL.rstrip('/')
    return f'{base}/auth/reset-password?uid={encode_uid(user)}&token={make_token(user)}'
