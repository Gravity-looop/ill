from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Q, Sum
from django.utils import timezone

from accounts.models import Account

from .models import BalanceEntry, PaymentRequest, Submission, WithdrawalRequest


class PaymentSubmissionError(Exception):
    pass


class SubmissionReviewError(Exception):
    pass


class SubmissionAmountMismatchError(SubmissionReviewError):
    pass


class WithdrawalError(Exception):
    pass


class WithdrawalBalanceError(WithdrawalError):
    pass


class WithdrawalAmountMismatchError(WithdrawalError):
    pass


def delete_stored_files(files):
    for stored_file in files:
        stored_file.delete(save=False)


@transaction.atomic
def create_submission(
    *,
    user,
    payment_request,
    screenshot,
    text,
    proposed_amount=None,
):
    request = PaymentRequest.objects.select_for_update().get(pk=payment_request.pk)

    if request.status != PaymentRequest.Status.PUBLISHED:
        raise PaymentSubmissionError("This payment request is closed.")

    if Submission.objects.filter(
        user=user,
        payment_request=request,
        status=Submission.Status.ACCEPTED,
    ).exists():
        raise PaymentSubmissionError(
            "This request has already been accepted for your account."
        )

    if Submission.objects.filter(
        user=user,
        payment_request=request,
        status=Submission.Status.PENDING,
    ).exists():
        raise PaymentSubmissionError(
            "You already have a pending submission for this request."
        )

    if request.amount is not None:
        proposed_amount = request.amount
    elif proposed_amount is None or proposed_amount <= 0:
        raise PaymentSubmissionError("Enter the amount you paid for this request.")

    latest_attempt = (
        Submission.objects.filter(user=user, payment_request=request).aggregate(
            maximum=Max("attempt"),
        )["maximum"]
        or 0
    )

    return Submission.objects.create(
        user=user,
        payment_request=request,
        screenshot=screenshot,
        proposed_amount=proposed_amount,
        text=text,
        attempt=latest_attempt + 1,
    )


@transaction.atomic
def accept_submission(*, submission_id, reviewer, final_amount):
    if final_amount is None or final_amount <= 0:
        raise SubmissionReviewError("A final amount greater than zero is required.")

    submission = (
        Submission.objects.select_for_update()
        .select_related("payment_request", "user")
        .get(pk=submission_id)
    )
    balance_entry = BalanceEntry.objects.filter(submission=submission).first()

    if submission.status == Submission.Status.ACCEPTED and balance_entry:
        if submission.final_amount != final_amount:
            raise SubmissionAmountMismatchError(
                "This submission was already accepted with a different amount."
            )
        return submission

    if submission.status != Submission.Status.PENDING:
        raise SubmissionReviewError("Only pending submissions can be accepted.")

    account, _ = Account.objects.select_for_update().get_or_create(user=submission.user)
    new_balance = account.balance + final_amount
    reviewed_at = timezone.now()

    account.balance = new_balance
    account.save(update_fields=("balance", "updated_at"))
    submission.status = Submission.Status.ACCEPTED
    submission.decline_reason = ""
    submission.final_amount = final_amount
    submission.reviewed_by = reviewer
    submission.reviewed_at = reviewed_at
    submission.save(
        update_fields=(
            "status",
            "decline_reason",
            "final_amount",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        )
    )
    BalanceEntry.objects.create(
        user=submission.user,
        amount=final_amount,
        balance_after=new_balance,
        submission=submission,
    )
    return submission


@transaction.atomic
def decline_submission(*, submission_id, reviewer, reason):
    submission = Submission.objects.select_for_update().get(pk=submission_id)

    if submission.status != Submission.Status.PENDING:
        raise SubmissionReviewError("Only pending submissions can be declined.")

    submission.status = Submission.Status.DECLINED
    submission.decline_reason = reason
    submission.reviewed_by = reviewer
    submission.reviewed_at = timezone.now()
    submission.save(
        update_fields=(
            "status",
            "decline_reason",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        )
    )
    return submission


@transaction.atomic
def force_delete_payment_request(*, payment_request_id):
    payment_request = PaymentRequest.objects.select_for_update().get(
        pk=payment_request_id
    )
    submissions = list(
        Submission.objects.select_for_update().filter(payment_request=payment_request)
    )
    submission_ids = [submission.id for submission in submissions]
    balance_entries = list(
        BalanceEntry.objects.select_for_update()
        .filter(submission_id__in=submission_ids)
        .values_list("id", "user_id")
    )
    account_ids = {user_id for _, user_id in balance_entries}
    accounts = list(Account.objects.select_for_update().filter(user_id__in=account_ids))
    files = [payment_request.qr_image]
    files.extend(submission.screenshot for submission in submissions)

    if balance_entries:
        BalanceEntry.objects.filter(
            id__in=[entry_id for entry_id, _ in balance_entries]
        ).delete()
    if submissions:
        Submission.objects.filter(id__in=submission_ids).delete()
    payment_request.delete()

    for account in accounts:
        account.balance = recalculate_account_balance(account.user_id)
        account.save(update_fields=("balance", "updated_at"))

    transaction.on_commit(lambda: delete_stored_files(files))


def recalculate_account_balance(user_id):
    totals = BalanceEntry.objects.filter(user_id=user_id).aggregate(
        credits=Sum(
            "amount",
            filter=Q(entry_type=BalanceEntry.EntryType.CREDIT),
        ),
        debits=Sum(
            "amount",
            filter=Q(entry_type=BalanceEntry.EntryType.DEBIT),
        ),
    )
    credits = totals["credits"] or Decimal("0.00")
    debits = totals["debits"] or Decimal("0.00")
    return credits - debits


def pending_withdrawal_total(user_id):
    return WithdrawalRequest.objects.filter(
        user_id=user_id,
        status=WithdrawalRequest.Status.PENDING,
    ).aggregate(total=Sum("total_amount"))["total"] or Decimal("0.00")


def available_balance(user):
    balance = user.account.balance
    pending = pending_withdrawal_total(user.id)
    return balance - pending


def withdrawal_balance_summary(user):
    balance = user.account.balance
    pending = pending_withdrawal_total(user.id)
    return {
        "balance": balance,
        "pending_amount": pending,
        "available_balance": balance - pending,
    }


@transaction.atomic
def create_withdrawal(*, user, payees, note=""):
    account, _ = Account.objects.select_for_update().get_or_create(user=user)
    total = sum((payee["amount"] for payee in payees), Decimal("0.00"))
    reserved = pending_withdrawal_total(user.id)

    if total > account.balance - reserved:
        raise WithdrawalBalanceError(
            "This request is higher than your available balance."
        )

    withdrawal = WithdrawalRequest.objects.create(
        user=user,
        total_amount=total,
        note=note,
    )
    for position, payee in enumerate(payees):
        withdrawal.payees.create(
            payee_name=payee["payee_name"],
            account_number=payee["account_number"],
            ifsc=payee["ifsc"],
            amount=payee["amount"],
            position=position,
        )
    withdrawal.reference = f"WDR-{withdrawal.pk:06d}"
    withdrawal.save(update_fields=("reference",))
    return withdrawal


@transaction.atomic
def confirm_withdrawal(*, withdrawal_id, reviewer, transaction_id, amount):
    transaction_id = (transaction_id or "").strip()
    if not transaction_id:
        raise WithdrawalError("A success transaction ID is required.")

    withdrawal = (
        WithdrawalRequest.objects.select_for_update()
        .select_related("user")
        .get(pk=withdrawal_id)
    )
    balance_entry = getattr(withdrawal, "balance_entry", None)

    if withdrawal.status == WithdrawalRequest.Status.PAID and balance_entry:
        if withdrawal.paid_transaction_id != transaction_id:
            raise WithdrawalAmountMismatchError(
                "This withdrawal was already paid with a different transaction ID."
            )
        if withdrawal.paid_amount != amount:
            raise WithdrawalAmountMismatchError(
                "This withdrawal was already paid with a different amount."
            )
        return withdrawal

    if withdrawal.status != WithdrawalRequest.Status.PENDING:
        raise WithdrawalError("Only pending withdrawals can be confirmed.")

    if amount != withdrawal.total_amount:
        raise WithdrawalAmountMismatchError(
            "The confirmed amount must match the requested total."
        )

    account, _ = Account.objects.select_for_update().get_or_create(user=withdrawal.user)
    if amount > account.balance:
        raise WithdrawalBalanceError(
            "This user no longer has enough balance for this payout."
        )

    new_balance = account.balance - amount
    account.balance = new_balance
    account.save(update_fields=("balance", "updated_at"))
    withdrawal.status = WithdrawalRequest.Status.PAID
    withdrawal.paid_transaction_id = transaction_id
    withdrawal.paid_amount = amount
    withdrawal.rejection_reason = ""
    withdrawal.processed_by = reviewer
    withdrawal.processed_at = timezone.now()
    withdrawal.save(
        update_fields=(
            "status",
            "paid_transaction_id",
            "paid_amount",
            "rejection_reason",
            "processed_by",
            "processed_at",
            "updated_at",
        )
    )
    BalanceEntry.objects.create(
        user=withdrawal.user,
        amount=amount,
        balance_after=new_balance,
        entry_type=BalanceEntry.EntryType.DEBIT,
        withdrawal=withdrawal,
    )
    return withdrawal


@transaction.atomic
def reject_withdrawal(*, withdrawal_id, reviewer, reason):
    withdrawal = WithdrawalRequest.objects.select_for_update().get(pk=withdrawal_id)

    if withdrawal.status != WithdrawalRequest.Status.PENDING:
        raise WithdrawalError("Only pending withdrawals can be rejected.")

    withdrawal.status = WithdrawalRequest.Status.REJECTED
    withdrawal.rejection_reason = reason
    withdrawal.processed_by = reviewer
    withdrawal.processed_at = timezone.now()
    withdrawal.save(
        update_fields=(
            "status",
            "rejection_reason",
            "processed_by",
            "processed_at",
            "updated_at",
        )
    )
    return withdrawal
