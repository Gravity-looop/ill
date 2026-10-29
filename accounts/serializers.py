from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class UserSerializer(serializers.ModelSerializer):
    balance = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        source="account.balance",
        read_only=True,
    )

    class Meta:
        model = User
        fields: tuple[str, ...] = (
            "id",
            "email",
            "first_name",
            "last_name",
            "balance",
        )
        read_only_fields = fields


class AdminUserSerializer(UserSerializer):
    submission_count = serializers.IntegerField(read_only=True)
    withdrawal_count = serializers.IntegerField(read_only=True)
    pending_withdrawal_amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    is_active = serializers.BooleanField(read_only=True)
    date_joined = serializers.DateTimeField(read_only=True)
    last_login = serializers.DateTimeField(read_only=True)

    class Meta(UserSerializer.Meta):
        fields: tuple[str, ...] = (
            "id",
            "email",
            "first_name",
            "last_name",
            "balance",
            "submission_count",
            "withdrawal_count",
            "pending_withdrawal_amount",
            "is_active",
            "is_staff",
            "date_joined",
            "last_login",
        )
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields: tuple[str, ...] = (
            "email",
            "password",
            "first_name",
            "last_name",
        )

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError(
                "An account with this email already exists."
            )
        return email

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class EmailTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        attrs["email"] = attrs["email"].strip().lower()
        data = super().validate(attrs)
        data["user"] = UserSerializer(self.user).data
        return data
