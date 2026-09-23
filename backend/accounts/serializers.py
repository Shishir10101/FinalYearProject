from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from .models import UserProfile
from .password_reset import decode_uid, check_token


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only view of a user's profile.

    ``role`` is the **resolved** role from ``core.permissions.get_role``, not the raw
    column. The two disagree for legacy rows: a user flagged ``is_staff`` with a
    default profile resolves to ``admin`` on the server, while the raw column still
    reads ``customer``. Publishing the raw value had the dashboard and the API
    disagreeing about the same user — the client was told "customer" while every
    request was authorised as "admin".

    Read-only either way. A writable ``role`` would let any customer PATCH
    themselves into a super admin.

    ``is_admin_user`` is kept so existing data and the Django admin filter still
    work, but it is **not** the dashboard's gate any more. It is only ever set for
    ``super_admin``/``admin`` (see ``UserProfile.save``), so gating on it locked
    **vendors** out entirely: the VENDOR role was enforced correctly by the API and
    had no way to reach a single screen. The role below is the gate.
    """

    role = serializers.SerializerMethodField()

    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'city', 'role', 'is_admin_user']
        read_only_fields = ['role', 'is_admin_user']

    def get_role(self, obj):
        from core.permissions import get_role
        return get_role(obj.user)


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']


class AdminUserSerializer(serializers.ModelSerializer):
    """A user as the admin dashboard's vendor form needs to see them.

    Deliberately narrow. This backs a **manager-only** endpoint, and the fields it
    does *not* carry are the point:

    * no ``password`` — a hash, even read-only, has no business in a JSON response;
    * no ``is_superuser`` / ``is_staff`` / ``permissions`` — the form attaches a shop
      to an account, it does not administer accounts;
    * ``role`` is **read-only**, resolved through ``get_role()`` so the dashboard
      and the server agree on what a user is. A writable ``role`` here would be a
      privilege-escalation hole: any manager could PATCH a customer to super admin.

    ``has_vendor`` is what makes the picker usable — a user who already owns a shop
    cannot own a second one (``Vendor.user`` is a ``OneToOneField``), so the form
    filters them out rather than offering a choice that would 400.
    """

    role = serializers.SerializerMethodField()
    has_vendor = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name',
                  'is_active', 'role', 'has_vendor']
        read_only_fields = fields

    def get_role(self, obj):
        from core.permissions import get_role
        return get_role(obj)

    def get_has_vendor(self, obj):
        """Whether this user already owns a shop.

        The view annotates this with an ``EXISTS`` subquery, so the whole list costs
        one query rather than one per row. The fallback keeps the serializer honest
        if it is ever used without that annotation — a reverse ``OneToOne`` raises
        rather than returning ``None`` when absent, which is easy to get wrong.
        """
        annotated = getattr(obj, 'has_vendor', None)
        if annotated is not None:
            return bool(annotated)
        from products.models import Vendor
        return Vendor.objects.filter(user=obj).exists()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)
    password2 = serializers.CharField(write_only=True, min_length=6)
    phone = serializers.CharField(max_length=15, required=False, default='')
    address = serializers.CharField(required=False, default='')
    city = serializers.CharField(max_length=20, required=False, default='kathmandu')

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'password2', 'first_name', 'last_name',
                  'phone', 'address', 'city']

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError({"password": "Passwords do not match."})
        if User.objects.filter(email=data['email']).exists():
            raise serializers.ValidationError({"email": "Email already registered."})
        return data

    def create(self, validated_data):
        phone = validated_data.pop('phone', '')
        address = validated_data.pop('address', '')
        city = validated_data.pop('city', 'kathmandu')
        validated_data.pop('password2')

        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', ''),
        )
        UserProfile.objects.create(
            user=user,
            phone=phone,
            address=address,
            city=city,
        )
        return user


class ProfileUpdateSerializer(serializers.ModelSerializer):
    phone = serializers.CharField(source='profile.phone', required=False)
    address = serializers.CharField(source='profile.address', required=False)
    city = serializers.CharField(source='profile.city', required=False)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'address', 'city']

    def update(self, instance, validated_data):
        profile_data = validated_data.pop('profile', {})
        instance.first_name = validated_data.get('first_name', instance.first_name)
        instance.last_name = validated_data.get('last_name', instance.last_name)
        instance.email = validated_data.get('email', instance.email)
        instance.save()

        profile = instance.profile
        if 'phone' in profile_data:
            profile.phone = profile_data['phone']
        if 'address' in profile_data:
            profile.address = profile_data['address']
        if 'city' in profile_data:
            profile.city = profile_data['city']
        profile.save()

        return instance


INVALID_LINK_MESSAGE = 'This reset link is invalid or has expired. Please request a new one.'


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Validates a reset link and the replacement password.

    The new password is checked with Django's configured validators
    (``AUTH_PASSWORD_VALIDATORS``), not just a length rule, so a reset cannot be
    used to set a password weaker than registration would have allowed.
    """

    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(write_only=True)
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError(
                {'new_password2': 'The two passwords do not match.'}
            )

        # A bad uid and a bad token produce the identical message. Distinguishing
        # them would let a caller probe which account ids are real.
        user = decode_uid(data['uid'])
        if user is None or not check_token(user, data['token']):
            raise serializers.ValidationError({'token': INVALID_LINK_MESSAGE})

        try:
            validate_password(data['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})

        data['user'] = user
        return data

    def save(self, **kwargs):
        user = self.validated_data['user']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user


class PasswordChangeSerializer(serializers.Serializer):
    """Change the password of an already-authenticated user.

    **Why this exists.** Until now the only way to change a password was the
    forgot-password flow, which requires access to the account's email and asserts
    you *forgot* the password. A signed-in customer who simply wanted a different
    password had no screen and no endpoint at all — so the only remedy for "I want
    to change my password" was to pretend to have lost it.

    **Why the current password is required.** This is the difference between a
    convenience and a hole. The caller is already authenticated, so without
    `current_password` any stolen access token could be escalated into permanent
    account takeover: the thief would change the password and lock the owner out
    for good. With it, a stolen token alone is not enough — and note that the
    forgotten-password flow does *not* have this problem, because possessing an
    emailed reset link is itself proof of mailbox control.

    Not a `ModelSerializer`: there is no model field to write directly, and the
    password never round-trips through the API.
    """

    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, data):
        user = self.context['request'].user

        if not user.check_password(data['current_password']):
            # The same message whether the account has a usable password or not. A
            # user created by `createsuperuser` always does; one created some other
            # way might not, and a distinct "no password set" reply would describe
            # the account's internals to whoever asked.
            raise serializers.ValidationError(
                {'current_password': 'That is not your current password.'}
            )

        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError(
                {'new_password2': 'The two passwords do not match.'}
            )

        if data['new_password'] == data['current_password']:
            # Rejected rather than silently accepted. "Changed" implies something
            # changed, and a no-op that reports success is the kind of dishonest
            # confirmation this project keeps having to remove.
            raise serializers.ValidationError(
                {'new_password': 'Your new password must be different from your '
                                 'current one.'}
            )

        # Django's configured validators, not a length rule — the same treatment
        # reset and registration get, so this cannot set a weaker password than
        # either of them would allow.
        try:
            validate_password(data['new_password'], user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'new_password': list(exc.messages)})

        return data

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user
