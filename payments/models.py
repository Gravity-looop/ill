import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


def qr_image_path(_instance, filename):
    extension = Path(filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".image"
    return f"payment-requests/{uuid.uuid4().hex}/qr{extension}"


def submission_screenshot_path(_instance, filename):
    extension = Path(filename).suffix.lower()
    if extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        extension = ".image"
    return f"submissions/{uuid.uuid4().hex}/screenshot{extension}"


class PaymentRequest(models.Model):
    class Status(models.TextChoices):
        PUBLISHED = "PUBLISHED", "Published"
        CLOSED = "CLOSED", "Closed"

    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    transaction_id = models.CharField(max_length=100, unique=True)
    qr_image = models.ImageField(upload_to=qr_image_path)
    instructions = models.TextField(blank=True, max_length=2000)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PUBLISHED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="payment_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return self.transaction_id


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        ACCEPTED = "ACCEPTED", "Accepted"
        DECLINED = "DECLINED", "Declined"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    payment_request = models.ForeignKey(
        PaymentRequest,
        on_delete=models.PROTECT,
        related_name="submissions",
    )
    screenshot = models.ImageField(upload_to=submission_screenshot_path)
    proposed_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    text = models.TextField(max_length=2000)
    attempt = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    decline_reason = models.TextField(blank=True, max_length=2000)
    final_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="reviewed_submissions",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "payment_request"),
                condition=models.Q(status="PENDING"),
                name="uniq_pending_user_request",
            ),
            models.UniqueConstraint(
                fields=("user", "payment_request"),
                condition=models.Q(status="ACCEPTED"),
                name="uniq_accepted_user_request",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status__in=("PENDING", "DECLINED"),
                        final_amount__isnull=True,
                    )
                    | models.Q(status="ACCEPTED", final_amount__isnull=False)
                ),
                name="submission_final_amount_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "payment_request")),
            models.Index(fields=("status", "created_at")),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.payment_request.transaction_id}"


class WithdrawalRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PAID = "PAID", "Paid"
        REJECTED = "REJECTED", "Rejected"

    reference = models.CharField(max_length=24, unique=True, null=True, blank=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="withdrawal_requests",
    )
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    note = models.TextField(blank=True, max_length=2000)
    paid_transaction_id = models.CharField(max_length=100, blank=True)
    paid_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    rejection_reason = models.TextField(blank=True, max_length=2000)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="processed_withdrawals",
        null=True,
        blank=True,
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status="PENDING",
                        paid_amount__isnull=True,
                        paid_transaction_id="",
                        processed_at__isnull=True,
                    )
                    | models.Q(
                        status="REJECTED",
                        paid_amount__isnull=True,
                        paid_transaction_id="",
                        processed_at__isnull=False,
                    )
                    | (
                        models.Q(
                            status="PAID",
                            paid_amount__isnull=False,
                            processed_at__isnull=False,
                        )
                        & ~models.Q(paid_transaction_id="")
                    )
                ),
                name="withdrawal_payment_matches_status",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "created_at")),
            models.Index(fields=("status", "created_at")),
        ]

    def __str__(self):
        return f"{self.reference}: {self.user.email} {self.total_amount}"


class WithdrawalPayee(models.Model):
    withdrawal = models.ForeignKey(
        WithdrawalRequest,
        on_delete=models.CASCADE,
        related_name="payees",
    )
    payee_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=34)
    ifsc = models.CharField(max_length=11)
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    position = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("withdrawal", "account_number"),
                name="uniq_account_number_per_withdrawal",
            ),
        ]

    def __str__(self):
        return f"{self.payee_name} - {self.account_number}"


class BalanceEntry(models.Model):
    class EntryType(models.TextChoices):
        CREDIT = "CREDIT", "Credit"
        DEBIT = "DEBIT", "Debit"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="balance_entries",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    balance_after = models.DecimalField(max_digits=16, decimal_places=2)
    entry_type = models.CharField(
        max_length=10,
        choices=EntryType.choices,
        default=EntryType.CREDIT,
    )
    submission = models.OneToOneField(
        Submission,
        on_delete=models.PROTECT,
        related_name="balance_entry",
        null=True,
        blank=True,
    )
    withdrawal = models.OneToOneField(
        WithdrawalRequest,
        on_delete=models.PROTECT,
        related_name="balance_entry",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(
                        entry_type="CREDIT",
                        submission__isnull=False,
                        withdrawal__isnull=True,
                    )
                    | models.Q(
                        entry_type="DEBIT",
                        submission__isnull=True,
                        withdrawal__isnull=False,
                    )
                ),
                name="balance_entry_source_matches_type",
            ),
        ]
        indexes = [models.Index(fields=("user", "created_at"))]

    def __str__(self):
        sign = "-" if self.entry_type == self.EntryType.DEBIT else ""
        return f"{self.user.email}: {sign}{self.amount}"
