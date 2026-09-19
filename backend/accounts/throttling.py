"""Rate limits for the credential-handling endpoints.

Scoped rather than global: ``DEFAULT_THROTTLE_CLASSES`` would apply these limits
to the entire API, which would break normal browsing. The password-reset
endpoints are the only ones where an unauthenticated caller can (a) cause an
outbound email and (b) repeatedly test reset tokens, so they are the only ones
that need a limit today.
"""

from rest_framework.throttling import AnonRateThrottle


class PasswordResetThrottle(AnonRateThrottle):
    """Throttles anonymous password-reset traffic per client IP.

    Rate is ``password_reset`` in ``REST_FRAMEWORK['DEFAULT_THROTTLE_RATES']``.
    """

    scope = 'password_reset'
