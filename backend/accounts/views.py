from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.conf import settings
from django.contrib.auth.models import User
from django.core.mail import send_mail
import logging

from .serializers import (
    RegisterSerializer, UserSerializer, ProfileUpdateSerializer,
    PasswordResetRequestSerializer, PasswordResetConfirmSerializer,
)
from .password_reset import build_reset_url
from .throttling import PasswordResetThrottle

logger = logging.getLogger(__name__)


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response({
            "message": "Registration successful",
            "user": UserSerializer(user).data
        }, status=status.HTTP_201_CREATED)


class ProfileView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user).data)


class PasswordResetRequestView(APIView):
    """Start a password reset.

    Always answers with the same 200 and the same wording, whether or not the
    address belongs to an account. Returning "no such email" here would turn the
    endpoint into a free account-enumeration service.

    A mail failure is logged rather than surfaced for the same reason: a 500 only
    ever happens when an account matched, so the error itself would leak the very
    fact the generic message is hiding.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    GENERIC_MESSAGE = (
        'If an account exists for that email address, a password reset link '
        'has been sent. Please check your inbox.'
    )

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']

        # Email is unique in practice (registration rejects duplicates) but not at
        # the database level, so this takes the first match rather than assuming
        # one exists. An admin-created duplicate would need handling separately.
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        payload = {'message': self.GENERIC_MESSAGE}

        if user is not None:
            reset_url = build_reset_url(user)
            self._send(user, reset_url)

            # Development convenience only. See PASSWORD_RESET_EXPOSE_LINK.
            if getattr(settings, 'PASSWORD_RESET_EXPOSE_LINK', False):
                payload['reset_url'] = reset_url
                payload['dev_note'] = (
                    'Development build only: this link is returned in the response '
                    'because no mailbox is configured. It is never returned when '
                    'PASSWORD_RESET_EXPOSE_LINK is off.'
                )

        return Response(payload)

    def _send(self, user, reset_url):
        subject = 'Reset your Puja Samagri Store password'
        # Read from the setting rather than hardcoding, so the email cannot claim
        # a different lifetime than the token actually has.
        hours = settings.PASSWORD_RESET_TIMEOUT // 3600
        message = (
            f'Namaste {user.get_short_name() or user.username},\n\n'
            f'Someone asked to reset the password for your Puja Samagri Store account.\n'
            f'Open the link below to choose a new one:\n\n'
            f'{reset_url}\n\n'
            f'The link expires in {hours} hours and stops working once it has been used.\n'
            f'If you did not request this, you can safely ignore this email - your\n'
            f'password has not been changed.\n'
        )
        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception:
            logger.exception('Password reset email failed for user id %s', user.pk)


class PasswordResetConfirmView(APIView):
    """Finish a password reset with a uid + token from the emailed link.

    Note on session invalidation: this changes the password but cannot revoke
    already-issued JWTs. Access tokens last one day and are stateless, so anyone
    holding a stolen token keeps it until it expires. Real revocation needs a
    token blacklist or a per-user token version — deliberately out of scope here
    and recorded as a known limitation rather than implied to be handled.
    """

    permission_classes = [permissions.AllowAny]
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({
            'message': 'Your password has been reset. You can now sign in with your new password.'
        })
