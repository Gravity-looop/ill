from decimal import Decimal

from django.urls import reverse
from rest_framework import serializers

from accounts.serializers import UserSerializer

from .models import (
    BalanceEntry,
    PaymentRequest,
    Submission,
    WithdrawalPayee,
    WithdrawalRequest,
)
from .services import (
    PaymentSubmissionError,
    WithdrawalBalanceError,
    WithdrawalError,
    create_submission,
    create_withdrawal,
)
from .validators import (
    MAX_PAYEES_PER_REQUEST,
    validate_account_number,
    validate_ifsc,
    validate_payee_name,
    validate_uploaded_image,
)


class PaymentRequestSerializer(serializers.ModelSerializer):
    qr_image_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentRequest
        fields: tuple[str, ...] = (
            "id",
            "amount",
            "transaction_id",
            "instructions",
            "status",
            "qr_image_url",
            "created_at",
        )
        read_only_fields = fields

    def get_qr_image_url(self, obj):
        if not obj.pk:
            return None
        path = reverse("payment-request-qr", kwargs={"pk": obj.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class AdminPaymentRequestSerializer(PaymentRequestSerializer):
    created_by = UserSerializer(read_only=True)
    submission_count = serializers.IntegerField(read_only=True)

    class Meta(PaymentRequestSerializer.Meta):
        fields: tuple[str, ...] = (
            "id",
            "amount",
            "transaction_id",
            "qr_image",
            "instructions",
            "status",
            "qr_image_url",
            "created_by",
            "submission_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "qr_image_url",
            "created_by",
            "submission_count",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"amount": {"allow_null": True}}

    def to_internal_value(self, data):
        if data.get("amount") == "":
            data = data.copy()
            data["amount"] = None
        return super().to_internal_value(data)

    def validate_amount(self, value):
        if value is None:
            return value
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        if value.as_tuple().exponent < -2:
            raise serializers.ValidationError(
                "Amount must have no more than 2 decimal places."
            )
        return value

    def validate_transaction_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Transaction ID is required.")
        return value

    def validate_qr_image(self, value):
        return validate_uploaded_image(value)

    def create(self, validated_data):
        return PaymentRequest.objects.create(
            created_by=self.context["request"].user,
            **validated_data,
        )


class SubmissionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    payment_request = PaymentRequestSerializer(read_only=True)
    screenshot_url = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields: tuple[str, ...] = (
            "id",
            "user",
            "payment_request",
            "screenshot_url",
            "proposed_amount",
            "text",
            "attempt",
            "status",
            "decline_reason",
            "final_amount",
            "reviewed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_screenshot_url(self, obj):
        if not obj.pk:
            return None
        path = reverse("submission-screenshot", kwargs={"pk": obj.pk})
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class SubmissionCreateSerializer(serializers.Serializer):
    screenshot = serializers.ImageField()
    proposed_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        required=False,
        allow_null=True,
    )
    text = serializers.CharField(max_length=2000)

    def validate_screenshot(self, value):
        return validate_uploaded_image(value)

    def validate_text(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Text is required.")
        return value

    def validate(self, attrs):
        payment_request = self.context["payment_request"]
        proposed_amount = attrs.get("proposed_amount")

        if payment_request.amount is not None:
            if (
                proposed_amount is not None
                and proposed_amount != payment_request.amount
            ):
                raise serializers.ValidationError(
                    {"proposed_amount": "This request has a fixed amount."}
                )
            attrs["proposed_amount"] = payment_request.amount
        elif proposed_amount is None:
            raise serializers.ValidationError(
                {"proposed_amount": ("Enter the amount you paid for this request.")}
            )
        return attrs

    def create(self, validated_data):
        try:
            return create_submission(
                user=self.context["request"].user,
                payment_request=self.context["payment_request"],
                **validated_data,
            )
        except PaymentSubmissionError as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class SubmissionAcceptSerializer(serializers.Serializer):
    final_amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )


class DeclineSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A decline reason is required.")
        return value


class BalanceEntrySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    payment_request_id = serializers.IntegerField(
        source="submission.payment_request_id",
        read_only=True,
        default=None,
    )
    submission_id = serializers.IntegerField(read_only=True)
    withdrawal_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = BalanceEntry
        fields: tuple[str, ...] = (
            "id",
            "user",
            "amount",
            "balance_after",
            "entry_type",
            "payment_request_id",
            "submission_id",
            "withdrawal_id",
            "created_at",
        )
        read_only_fields = fields


class WithdrawalBalanceSerializer(serializers.Serializer):
    balance = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    pending_amount = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )
    available_balance = serializers.DecimalField(
        max_digits=16,
        decimal_places=2,
        read_only=True,
    )

    def create(self, validated_data):
        raise NotImplementedError

    def update(self, instance, validated_data):
        raise NotImplementedError


class WithdrawalPayeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WithdrawalPayee
        fields: tuple[str, ...] = (
            "id",
            "payee_name",
            "account_number",
            "ifsc",
            "amount",
            "position",
        )
        read_only_fields = fields


class WithdrawalRequestSerializer(serializers.ModelSerializer):
    payees = WithdrawalPayeeSerializer(many=True, read_only=True)
    payee_count = serializers.SerializerMethodField()

    class Meta:
        model = WithdrawalRequest
        fields: tuple[str, ...] = (
            "id",
            "reference",
            "total_amount",
            "status",
            "note",
            "payees",
            "payee_count",
            "paid_transaction_id",
            "paid_amount",
            "rejection_reason",
            "processed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields

    def get_payee_count(self, obj):
        return len(obj.payees.all())


class AdminWithdrawalRequestSerializer(WithdrawalRequestSerializer):
    user = UserSerializer(read_only=True)
    processed_by = UserSerializer(read_only=True)

    class Meta(WithdrawalRequestSerializer.Meta):
        fields: tuple[str, ...] = (
            "id",
            "reference",
            "user",
            "total_amount",
            "status",
            "note",
            "payees",
            "payee_count",
            "paid_transaction_id",
            "paid_amount",
            "rejection_reason",
            "processed_by",
            "processed_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = fields


class WithdrawalSummarySerializer(serializers.Serializer):
    count = serializers.IntegerField(read_only=True)
    pending_count = serializers.IntegerField(read_only=True)
    latest_id = serializers.IntegerField(read_only=True, allow_null=True)
    latest_created_at = serializers.DateTimeField(read_only=True, allow_null=True)
    latest_processed_at = serializers.DateTimeField(read_only=True, allow_null=True)

    def create(self, validated_data):
        raise NotImplementedError

    def update(self, instance, validated_data):
        raise NotImplementedError


class WithdrawalPayeeInputSerializer(serializers.Serializer):
    payee_name = serializers.CharField(max_length=100)
    account_number = serializers.CharField(max_length=34)
    ifsc = serializers.CharField(max_length=11)
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate_payee_name(self, value):
        return validate_payee_name(value)

    def validate_account_number(self, value):
        return validate_account_number(value)

    def validate_ifsc(self, value):
        return validate_ifsc(value)

    def validate(self, attrs):
        seen = self.context.get("seen_account_numbers")
        if seen is None:
            seen = set()
            self.context["seen_account_numbers"] = seen
        account_number = attrs["account_number"]
        if account_number in seen:
            raise serializers.ValidationError(
                "Each payee must use a different account number."
            )
        seen.add(account_number)
        return attrs


class WithdrawalCreateSerializer(serializers.Serializer):
    note = serializers.CharField(
        max_length=2000,
        required=False,
        allow_blank=True,
        default="",
    )
    payees = WithdrawalPayeeInputSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        payees = attrs["payees"]
        if len(payees) > MAX_PAYEES_PER_REQUEST:
            raise serializers.ValidationError(
                {
                    "payees": (
                        f"A withdrawal request can have up to "
                        f"{MAX_PAYEES_PER_REQUEST} payees."
                    )
                }
            )
        if sum(payee["amount"] for payee in payees) <= 0:
            raise serializers.ValidationError(
                {"payees": "Enter an amount for at least one payee."}
            )
        return attrs

    def create(self, validated_data):
        try:
            return create_withdrawal(
                user=self.context["request"].user,
                note=validated_data.get("note", ""),
                payees=validated_data["payees"],
            )
        except (WithdrawalBalanceError, WithdrawalError) as exc:
            raise serializers.ValidationError({"detail": str(exc)}) from exc


class WithdrawalConfirmSerializer(serializers.Serializer):
    transaction_id = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
    )

    def validate_transaction_id(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A success transaction ID is required.")
        return value


class WithdrawalRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000)

    def validate_reason(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A rejection reason is required.")
        return value
