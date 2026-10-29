from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from PIL import Image
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import BalanceEntry, PaymentRequest, Submission, WithdrawalRequest


def make_image(name="proof.png", size=(32, 32)):
    content = BytesIO()
    Image.new("RGB", size, "blue").save(content, format="PNG")
    return SimpleUploadedFile(name, content.getvalue(), content_type="image/png")


class PaymentApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls.media_directory = TemporaryDirectory()
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_directory.name)
        cls.media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.media_override.disable()
        cls.media_directory.cleanup()

    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="user@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongPass123!",
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.authenticate(self.user)
        self.admin_client = self.client_class()
        self.authenticate_client(self.admin_client, self.admin)

    def authenticate_client(self, client, user):
        response = client.post(
            reverse("token-obtain-pair"),
            {"email": user.email, "password": "StrongPass123!"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def authenticate(self, user):
        self.authenticate_client(self.client, user)

    def create_payment_request(
        self,
        client=None,
        transaction_id="TXN-100",
        amount="125.50",
    ):
        client = client or self.admin_client
        payload = {
            "transaction_id": transaction_id,
            "instructions": "Send the exact amount.",
            "qr_image": make_image("qr.png"),
        }
        if amount is not None:
            payload["amount"] = amount
        return client.post(
            reverse("admin-payment-request-list"),
            payload,
            format="multipart",
        )

    def submit_proof(
        self,
        payment_request,
        text="Payment completed",
        proposed_amount=None,
    ):
        payload = {
            "screenshot": make_image(),
            "text": text,
        }
        if proposed_amount is not None:
            payload["proposed_amount"] = proposed_amount
        return self.client.post(
            reverse("submission-create", kwargs={"pk": payment_request.id}),
            payload,
            format="multipart",
        )

    def accept_submission(self, submission_id, final_amount="125.50"):
        return self.admin_client.post(
            reverse("admin-submission-accept", kwargs={"pk": submission_id}),
            {"final_amount": final_amount},
            format="json",
        )

    def force_delete_request(
        self,
        payment_request,
        confirmation=None,
        client=None,
    ):
        client = client or self.admin_client
        return client.delete(
            reverse(
                "admin-payment-request-force-delete",
                kwargs={"pk": payment_request.id},
            ),
            {
                "confirm_transaction_id": (
                    payment_request.transaction_id
                    if confirmation is None
                    else confirmation
                )
            },
            format="json",
        )

    def test_only_admin_can_create_payment_request(self):
        response = self.create_payment_request(client=self.client)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_only_admin_can_delete_payment_request(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        url = reverse(
            "admin-payment-request-detail",
            kwargs={"pk": payment_request.id},
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(PaymentRequest.objects.filter(pk=payment_request.id).exists())

    def test_admin_can_delete_unused_payment_request(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        qr_path = Path(payment_request.qr_image.path)

        response = self.admin_client.delete(
            reverse(
                "admin-payment-request-detail",
                kwargs={"pk": payment_request.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PaymentRequest.objects.filter(pk=payment_request.id).exists())
        self.assertFalse(qr_path.exists())

    def test_payment_request_with_submissions_cannot_be_deleted(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        self.submit_proof(payment_request)

        response = self.admin_client.delete(
            reverse(
                "admin-payment-request-detail",
                kwargs={"pk": payment_request.id},
            )
        )

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertTrue(PaymentRequest.objects.filter(pk=payment_request.id).exists())

    def test_only_admin_can_force_delete_payment_request(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()

        response = self.force_delete_request(
            payment_request,
            client=self.client,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(PaymentRequest.objects.filter(pk=payment_request.id).exists())

    def test_force_delete_requires_matching_transaction_id(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        self.submit_proof(payment_request)

        response = self.force_delete_request(
            payment_request,
            confirmation="WRONG-ID",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(PaymentRequest.objects.filter(pk=payment_request.id).exists())
        self.assertTrue(
            Submission.objects.filter(payment_request=payment_request).exists()
        )

    def test_admin_can_force_delete_request_with_submission(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        self.submit_proof(payment_request)
        submission = Submission.objects.get()
        qr_path = Path(payment_request.qr_image.path)
        screenshot_path = Path(submission.screenshot.path)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.force_delete_request(payment_request)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PaymentRequest.objects.filter(pk=payment_request.id).exists())
        self.assertFalse(Submission.objects.filter(pk=submission.id).exists())
        self.assertFalse(qr_path.exists())
        self.assertFalse(screenshot_path.exists())

    def test_force_delete_recalculates_credited_user_balance(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission_id = self.submit_proof(payment_request).data["id"]
        self.accept_submission(submission_id)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.force_delete_request(payment_request)

        self.user.account.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(self.user.account.balance, Decimal("0.00"))
        self.assertFalse(Submission.objects.filter(pk=submission_id).exists())
        self.assertFalse(
            BalanceEntry.objects.filter(submission_id=submission_id).exists()
        )

    def test_admin_creates_and_user_reads_published_request(self):
        create_response = self.create_payment_request()
        payment_request = PaymentRequest.objects.get()

        list_response = self.client.get(reverse("payment-request-list"))
        detail_response = self.client.get(
            reverse("payment-request-detail", kwargs={"pk": payment_request.id}),
        )

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)
        self.assertEqual(detail_response.data["amount"], "125.50")
        self.assertEqual(detail_response.data["transaction_id"], "TXN-100")
        self.assertIn("qr_image_url", detail_response.data)

    def test_user_submits_screenshot_and_text(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()

        response = self.submit_proof(payment_request)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], Submission.Status.PENDING)
        self.assertEqual(response.data["attempt"], 1)
        self.assertEqual(response.data["proposed_amount"], "125.50")
        self.assertIsNone(response.data["final_amount"])
        self.assertTrue(Submission.objects.filter(user=self.user).exists())

    def test_duplicate_pending_submission_is_rejected(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        self.submit_proof(payment_request)

        response = self.submit_proof(payment_request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Submission.objects.filter(user=self.user).count(), 1)

    def test_declined_submission_can_be_resubmitted(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        first_response = self.submit_proof(payment_request)
        submission_id = first_response.data["id"]

        decline_response = self.admin_client.post(
            reverse("admin-submission-decline", kwargs={"pk": submission_id}),
            {"reason": "Screenshot is unclear."},
            format="json",
        )
        second_response = self.submit_proof(payment_request, "Corrected screenshot")

        self.assertEqual(decline_response.status_code, status.HTTP_200_OK)
        self.assertEqual(decline_response.data["status"], Submission.Status.DECLINED)
        self.assertEqual(second_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second_response.data["attempt"], 2)

    def test_accepting_submission_credits_exact_amount_once(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission = self.submit_proof(payment_request).data["id"]

        first_response = self.accept_submission(submission)
        second_response = self.accept_submission(submission)
        history_response = self.client.get(reverse("balance-history"))
        self.user.account.refresh_from_db()

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(first_response.data["status"], Submission.Status.ACCEPTED)
        self.assertEqual(first_response.data["final_amount"], "125.50")
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account.balance, Decimal("125.50"))
        self.assertEqual(BalanceEntry.objects.filter(user=self.user).count(), 1)
        self.assertEqual(
            history_response.data["results"][0]["submission_id"], submission
        )

    def test_accepted_request_cannot_be_submitted_again(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission = self.submit_proof(payment_request).data["id"]
        self.accept_submission(submission)

        response = self.submit_proof(payment_request)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_submission_file_is_private(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission_id = self.submit_proof(payment_request).data["id"]
        url = reverse("submission-screenshot", kwargs={"pk": submission_id})

        owner_response = self.client.get(url)
        self.authenticate(self.other_user)
        other_response = self.client.get(url)
        admin_response = self.admin_client.get(url)

        self.assertEqual(owner_response.status_code, status.HTTP_200_OK)
        self.assertEqual(other_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(admin_response.status_code, status.HTTP_200_OK)
        owner_response.close()
        other_response.close()
        admin_response.close()

    def test_closed_request_rejects_new_submissions(self):
        create_response = self.create_payment_request()
        payment_request_id = create_response.data["id"]
        close_response = self.admin_client.patch(
            reverse("admin-payment-request-detail", kwargs={"pk": payment_request_id}),
            {"status": PaymentRequest.Status.CLOSED},
            format="json",
        )
        payment_request = PaymentRequest.objects.get(pk=payment_request_id)

        submit_response = self.submit_proof(payment_request)
        list_response = self.client.get(reverse("payment-request-list"))

        self.assertEqual(close_response.status_code, status.HTTP_200_OK)
        self.assertEqual(submit_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(list_response.data["count"], 0)

    def test_existing_pending_submission_can_be_accepted_after_close(self):
        create_response = self.create_payment_request()
        payment_request_id = create_response.data["id"]
        payment_request = PaymentRequest.objects.get(pk=payment_request_id)
        submission_id = self.submit_proof(payment_request).data["id"]
        self.admin_client.patch(
            reverse("admin-payment-request-detail", kwargs={"pk": payment_request_id}),
            {"status": PaymentRequest.Status.CLOSED},
            format="json",
        )

        response = self.accept_submission(submission_id)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], Submission.Status.ACCEPTED)

    def test_admin_can_filter_submissions(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        self.submit_proof(payment_request)

        response = self.admin_client.get(
            reverse("admin-submission-list"),
            {"status": Submission.Status.PENDING},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["user"]["email"], self.user.email)

    def test_admin_can_create_request_without_fixed_amount(self):
        create_response = self.create_payment_request(
            transaction_id="TXN-OPEN",
            amount="",
        )
        payment_request = PaymentRequest.objects.get(pk=create_response.data["id"])

        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        self.assertIsNone(create_response.data["amount"])
        self.assertIsNone(payment_request.amount)

    def test_admin_can_clear_fixed_amount_on_update(self):
        create_response = self.create_payment_request()
        payment_request_id = create_response.data["id"]

        response = self.admin_client.patch(
            reverse(
                "admin-payment-request-detail",
                kwargs={"pk": payment_request_id},
            ),
            {"amount": ""},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsNone(response.data["amount"])
        payment_request = PaymentRequest.objects.get(pk=payment_request_id)
        self.assertIsNone(payment_request.amount)

    def test_open_request_requires_and_stores_user_amount(self):
        self.create_payment_request(transaction_id="TXN-OPEN", amount=None)
        payment_request = PaymentRequest.objects.get()

        missing_response = self.submit_proof(payment_request)
        response = self.submit_proof(payment_request, proposed_amount="75.25")

        self.assertEqual(missing_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("proposed_amount", missing_response.data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["proposed_amount"], "75.25")
        self.assertIsNone(response.data["final_amount"])

    def test_acceptance_requires_final_amount_and_credits_it(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission_id = self.submit_proof(payment_request).data["id"]

        missing_response = self.admin_client.post(
            reverse("admin-submission-accept", kwargs={"pk": submission_id}),
        )
        response = self.accept_submission(submission_id, final_amount="130.00")
        submission = Submission.objects.get(pk=submission_id)
        self.user.account.refresh_from_db()

        self.assertEqual(missing_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("final_amount", missing_response.data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["final_amount"], "130.00")
        self.assertEqual(submission.final_amount, Decimal("130.00"))
        self.assertEqual(self.user.account.balance, Decimal("130.00"))
        self.assertEqual(
            BalanceEntry.objects.get(submission_id=submission_id).amount,
            Decimal("130.00"),
        )

    def test_admin_final_amount_overrides_user_proposed_amount(self):
        self.create_payment_request(transaction_id="TXN-OPEN", amount=None)
        payment_request = PaymentRequest.objects.get()
        submission_id = self.submit_proof(
            payment_request,
            proposed_amount="75.25",
        ).data["id"]

        response = self.accept_submission(submission_id, final_amount="80.00")
        submission = Submission.objects.get(pk=submission_id)
        self.user.account.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(submission.proposed_amount, Decimal("75.25"))
        self.assertEqual(submission.final_amount, Decimal("80.00"))
        self.assertEqual(self.user.account.balance, Decimal("80.00"))
        self.assertEqual(
            BalanceEntry.objects.get(submission_id=submission_id).amount,
            Decimal("80.00"),
        )

    def test_accepted_submission_amount_cannot_be_changed(self):
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()
        submission_id = self.submit_proof(payment_request).data["id"]
        self.accept_submission(submission_id, final_amount="130.00")

        response = self.accept_submission(submission_id, final_amount="131.00")
        self.user.account.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(self.user.account.balance, Decimal("130.00"))
        self.assertEqual(
            BalanceEntry.objects.filter(submission_id=submission_id).count(), 1
        )

    def test_invalid_image_is_rejected(self):
        invalid_image = SimpleUploadedFile(
            "proof.png",
            b"not-an-image",
            content_type="image/png",
        )
        self.create_payment_request()
        payment_request = PaymentRequest.objects.get()

        response = self.client.post(
            reverse("submission-create", kwargs={"pk": payment_request.id}),
            {"screenshot": invalid_image, "text": "Proof"},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("screenshot", response.data)

    def test_amount_with_more_than_two_decimals_is_rejected(self):
        response = self.admin_client.post(
            reverse("admin-payment-request-list"),
            {
                "amount": "10.999",
                "transaction_id": "TXN-101",
                "qr_image": make_image(),
            },
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("amount", response.data)


class WithdrawalApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            email="payer@example.com",
            password="StrongPass123!",
        )
        self.other_user = User.objects.create_user(
            email="other@example.com",
            password="StrongPass123!",
        )
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password="StrongPass123!",
            is_staff=True,
        )
        self.fund("1000.00")
        self.authenticate_client(self.client, self.user)
        self.admin_client = self.client_class()
        self.authenticate_client(self.admin_client, self.admin)

    def authenticate_client(self, client, user):
        response = client.post(
            reverse("token-obtain-pair"),
            {"email": user.email, "password": "StrongPass123!"},
            format="json",
        )
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def fund(self, amount, user=None):
        account = (user or self.user).account
        account.balance = Decimal(amount)
        account.save(update_fields=("balance", "updated_at"))
        return account

    def payee(self, **overrides):
        payee = {
            "payee_name": "Ravi Kumar",
            "account_number": "123456789012",
            "ifsc": "HDFC0001234",
            "amount": "100.00",
        }
        payee.update(overrides)
        return payee

    def create_withdrawal(self, payees=None, note="Monthly payout", client=None):
        return (client or self.client).post(
            reverse("withdrawal-list"),
            {"payees": payees or [self.payee()], "note": note},
            format="json",
        )

    def confirm_withdrawal(
        self,
        withdrawal_id,
        transaction_id="NEFT-9001",
        amount="100.00",
        client=None,
    ):
        return (client or self.admin_client).post(
            reverse("admin-withdrawal-confirm", kwargs={"pk": withdrawal_id}),
            {"transaction_id": transaction_id, "amount": amount},
            format="json",
        )

    def test_create_withdrawal_with_multiple_payees(self):
        response = self.create_withdrawal(
            payees=[
                self.payee(amount="250.00"),
                self.payee(
                    payee_name="Anita Sharma",
                    account_number="987654321098",
                    ifsc="sbin0004321",
                    amount="150.00",
                ),
            ]
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_amount"], "400.00")
        self.assertEqual(response.data["status"], WithdrawalRequest.Status.PENDING)
        self.assertEqual(response.data["payee_count"], 2)
        self.assertEqual(len(response.data["payees"]), 2)
        self.assertTrue(response.data["reference"].startswith("WDR-"))
        self.assertEqual(
            [payee["ifsc"] for payee in response.data["payees"]],
            ["HDFC0001234", "SBIN0004321"],
        )
        self.user.account.refresh_from_db()
        self.assertEqual(self.user.account.balance, Decimal("1000.00"))
        self.assertEqual(BalanceEntry.objects.filter(user=self.user).count(), 0)

    def test_pending_withdrawal_reserves_balance(self):
        self.create_withdrawal(payees=[self.payee(amount="400.00")])

        response = self.client.get(reverse("withdrawal-balance"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["balance"], "1000.00")
        self.assertEqual(response.data["pending_amount"], "400.00")
        self.assertEqual(response.data["available_balance"], "600.00")

    def test_withdrawal_above_available_balance_is_rejected(self):
        self.create_withdrawal(payees=[self.payee(amount="700.00")])

        response = self.create_withdrawal(
            payees=[self.payee(account_number="555555555555", amount="400.00")],
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertEqual(WithdrawalRequest.objects.count(), 1)

    def test_duplicate_account_number_is_rejected(self):
        response = self.create_withdrawal(
            payees=[self.payee(), self.payee(payee_name="Ravi Kumar")],
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_invalid_ifsc_is_rejected(self):
        response = self.create_withdrawal(payees=[self.payee(ifsc="HDFC123")])

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_more_than_five_payees_is_rejected(self):
        payees = [self.payee(account_number=f"1000000000{index}") for index in range(6)]

        response = self.create_withdrawal(payees=payees)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(WithdrawalRequest.objects.count(), 0)

    def test_confirm_withdrawal_debits_balance(self):
        withdrawal_id = self.create_withdrawal(
            payees=[self.payee(amount="300.00")],
        ).data["id"]

        response = self.confirm_withdrawal(withdrawal_id, amount="300.00")
        withdrawal = WithdrawalRequest.objects.get(pk=withdrawal_id)
        self.user.account.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.PAID)
        self.assertEqual(withdrawal.paid_amount, Decimal("300.00"))
        self.assertEqual(withdrawal.paid_transaction_id, "NEFT-9001")
        self.assertEqual(withdrawal.processed_by, self.admin)
        self.assertIsNotNone(withdrawal.processed_at)
        self.assertEqual(self.user.account.balance, Decimal("700.00"))
        entry = BalanceEntry.objects.get(withdrawal_id=withdrawal_id)
        self.assertEqual(entry.entry_type, BalanceEntry.EntryType.DEBIT)
        self.assertEqual(entry.balance_after, Decimal("700.00"))
        self.assertIsNone(entry.submission_id)

    def test_confirming_twice_does_not_debit_twice(self):
        withdrawal_id = self.create_withdrawal().data["id"]
        self.confirm_withdrawal(withdrawal_id)

        response = self.confirm_withdrawal(withdrawal_id)
        self.user.account.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.account.balance, Decimal("900.00"))
        self.assertEqual(BalanceEntry.objects.filter(entry_type="DEBIT").count(), 1)

    def test_confirm_requires_matching_amount(self):
        withdrawal_id = self.create_withdrawal().data["id"]

        response = self.confirm_withdrawal(withdrawal_id, amount="50.00")
        self.user.account.refresh_from_db()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            WithdrawalRequest.objects.get(pk=withdrawal_id).status,
            WithdrawalRequest.Status.PENDING,
        )
        self.assertEqual(self.user.account.balance, Decimal("1000.00"))

    def test_rejected_withdrawal_releases_reserved_balance(self):
        withdrawal_id = self.create_withdrawal(
            payees=[self.payee(amount="400.00")],
        ).data["id"]

        response = self.admin_client.post(
            reverse("admin-withdrawal-reject", kwargs={"pk": withdrawal_id}),
            {"reason": "Account details need a correction."},
            format="json",
        )
        withdrawal = WithdrawalRequest.objects.get(pk=withdrawal_id)
        balance_response = self.client.get(reverse("withdrawal-balance"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(withdrawal.status, WithdrawalRequest.Status.REJECTED)
        self.assertEqual(
            withdrawal.rejection_reason,
            "Account details need a correction.",
        )
        self.assertIsNotNone(withdrawal.processed_at)
        self.assertIsNone(withdrawal.paid_amount)
        self.assertEqual(balance_response.data["available_balance"], "1000.00")
        self.assertEqual(BalanceEntry.objects.filter(entry_type="DEBIT").count(), 0)

    def test_paid_withdrawal_cannot_be_rejected(self):
        withdrawal_id = self.create_withdrawal().data["id"]
        self.confirm_withdrawal(withdrawal_id)

        response = self.admin_client.post(
            reverse("admin-withdrawal-reject", kwargs={"pk": withdrawal_id}),
            {"reason": "Changed my mind."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            WithdrawalRequest.objects.get(pk=withdrawal_id).status,
            WithdrawalRequest.Status.PAID,
        )

    def test_user_sees_only_own_withdrawals(self):
        withdrawal_id = self.create_withdrawal().data["id"]
        other_client = self.client_class()
        self.authenticate_client(other_client, self.other_user)

        detail = other_client.get(
            reverse("withdrawal-detail", kwargs={"pk": withdrawal_id}),
        )
        listing = other_client.get(reverse("withdrawal-list"))

        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data["count"], 0)

    def test_admin_can_list_and_filter_withdrawals(self):
        self.create_withdrawal()
        self.fund("500.00", user=self.other_user)
        other_client = self.client_class()
        self.authenticate_client(other_client, self.other_user)
        other_client.post(
            reverse("withdrawal-list"),
            {"payees": [self.payee(payee_name="Sunita Rao")]},
            format="json",
        )

        response = self.admin_client.get(
            reverse("admin-withdrawal-list"),
            {"status": WithdrawalRequest.Status.PENDING},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)

        search = self.admin_client.get(
            reverse("admin-withdrawal-list"),
            {"search": "Sunita"},
        )
        self.assertEqual(search.data["count"], 1)
        self.assertEqual(
            search.data["results"][0]["payees"][0]["payee_name"], "Sunita Rao"
        )

        forbidden = self.client.get(reverse("admin-withdrawal-list"))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_cannot_confirm_own_withdrawal(self):
        withdrawal_id = self.create_withdrawal().data["id"]

        response = self.confirm_withdrawal(withdrawal_id, client=self.client)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            WithdrawalRequest.objects.get(pk=withdrawal_id).status,
            WithdrawalRequest.Status.PENDING,
        )

    def test_admin_user_list_reports_withdrawal_totals(self):
        self.create_withdrawal(payees=[self.payee(amount="250.00")])

        response = self.admin_client.get(
            reverse("admin-user-list"),
            {"user_id": self.user.id},
        )
        record = next(
            item for item in response.data["results"] if item["id"] == self.user.id
        )

        self.assertEqual(record["withdrawal_count"], 1)
        self.assertEqual(record["pending_withdrawal_amount"], "250.00")
        self.assertEqual(record["submission_count"], 0)

    def test_balance_history_includes_debit_entry(self):
        withdrawal_id = self.create_withdrawal().data["id"]
        self.confirm_withdrawal(withdrawal_id)

        response = self.client.get(reverse("balance-history"))

        entry = response.data["results"][0]
        self.assertEqual(entry["entry_type"], "DEBIT")
        self.assertEqual(entry["withdrawal_id"], withdrawal_id)
        self.assertIsNone(entry["payment_request_id"])
        self.assertIsNone(entry["submission_id"])
        self.assertEqual(entry["balance_after"], "900.00")

    def summary(self, **params):
        return self.admin_client.get(
            reverse("admin-withdrawal-summary"), params or None
        )

    def test_summary_reports_totals_and_change_watermark(self):
        empty = self.summary()
        self.assertEqual(empty.status_code, status.HTTP_200_OK)
        self.assertEqual(empty.data["count"], 0)
        self.assertEqual(empty.data["pending_count"], 0)
        self.assertIsNone(empty.data["latest_id"])
        self.assertIsNone(empty.data["latest_created_at"])
        self.assertIsNone(empty.data["latest_processed_at"])

        created = self.create_withdrawal().data
        pending = self.summary()
        self.assertEqual(pending.data["count"], 1)
        self.assertEqual(pending.data["pending_count"], 1)
        self.assertEqual(pending.data["latest_id"], created["id"])
        self.assertIsNotNone(pending.data["latest_created_at"])
        self.assertIsNone(pending.data["latest_processed_at"])

        self.confirm_withdrawal(created["id"])
        paid = self.summary()
        self.assertEqual(paid.data["count"], 1)
        self.assertEqual(paid.data["pending_count"], 0)
        self.assertEqual(paid.data["latest_id"], created["id"])
        self.assertIsNotNone(paid.data["latest_processed_at"])

    def test_summary_watermark_advances_for_each_new_withdrawal(self):
        first = self.summary().data
        second_id = self.create_withdrawal(note="Second batch").data["id"]

        second = self.summary().data

        self.assertEqual(second["count"], 1)
        self.assertNotEqual(second["latest_id"], first["latest_id"])
        self.assertEqual(second["latest_id"], second_id)

    def test_summary_respects_admin_list_filters(self):
        self.create_withdrawal()
        self.fund("500.00", user=self.other_user)
        other_client = self.client_class()
        self.authenticate_client(other_client, self.other_user)
        other_created = other_client.post(
            reverse("withdrawal-list"),
            {"payees": [self.payee(payee_name="Sunita Rao")]},
            format="json",
        )
        self.confirm_withdrawal(other_created.data["id"])

        pending = self.summary(status=WithdrawalRequest.Status.PENDING)
        self.assertEqual(pending.data["count"], 1)
        self.assertEqual(pending.data["pending_count"], 1)

        paid = self.summary(status=WithdrawalRequest.Status.PAID)
        self.assertEqual(paid.data["count"], 1)
        self.assertEqual(paid.data["pending_count"], 0)

        searched = self.summary(search="Sunita")
        self.assertEqual(searched.data["count"], 1)

        by_user = self.summary(user_id=self.other_user.id)
        self.assertEqual(by_user.data["count"], 1)

        scoped = self.summary(
            user_id=self.user.id, status=WithdrawalRequest.Status.PAID
        )
        self.assertEqual(scoped.data["count"], 0)

        invalid = self.summary(status="NOPE")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_summary_requires_admin(self):
        self.create_withdrawal()

        forbidden = self.client.get(reverse("admin-withdrawal-summary"))
        self.assertEqual(forbidden.status_code, status.HTTP_403_FORBIDDEN)

        anonymous = self.client_class().get(reverse("admin-withdrawal-summary"))
        self.assertEqual(anonymous.status_code, status.HTTP_401_UNAUTHORIZED)
