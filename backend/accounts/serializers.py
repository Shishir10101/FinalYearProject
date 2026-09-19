from rest_framework import serializers
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileSerializer(serializers.ModelSerializer):
    """Read-only view of a user's profile.

    ``role`` is exposed but **read-only**. The dashboard needs it to decide which
    UI to render (a vendor must not be shown area management), and the storefront
    needs it to label the account. Making it writable would let any customer
    PATCH themselves into a super admin.
    """

    class Meta:
        model = UserProfile
        fields = ['phone', 'address', 'city', 'role', 'is_admin_user']
        read_only_fields = ['role', 'is_admin_user']


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'profile']


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
