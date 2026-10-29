import mimetypes
from decimal import Decimal

from django.db.models import Count, DecimalField, Max, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User
from accounts.serializers import AdminUserSerializer

from .models import BalanceEntry, PaymentRequest, Submission, WithdrawalRequest
from .serializers import (
    AdminPaymentRequestSerializer,
    AdminWithdrawalRequestSerializer,
    BalanceEntrySerializer,
    DeclineSerializer,
    PaymentRequestSerializer,
    SubmissionAcceptSerializer,
    SubmissionCreateSerializer,
    SubmissionSerializer,
    WithdrawalBalanceSerializer,
    WithdrawalConfirmSerializer,
    WithdrawalCreateSerializer,
    WithdrawalRejectSerializer,
    WithdrawalRequestSerializer,
    WithdrawalSummarySerializer,
)
from .services import (
    SubmissionAmountMismatchError,
    SubmissionReviewError,
    WithdrawalAmountMismatchError,
    WithdrawalBalanceError,
    WithdrawalError,
    accept_submission,
    available_balance,
    confirm_withdrawal,
    decline_submission,
    force_delete_payment_request,
    reject_withdrawal,
    withdrawal_balance_summary,
)


def annotate_user_withdrawal_totals(queryset):
    pending_total = (
        WithdrawalRequest.objects.filter(
            user=OuterRef("pk"),
            status=WithdrawalRequest.Status.PENDING,
        )
        .order_by()
        .values("user")
        .annotate(total=Sum("total_amount"))
        .values("total")[:1]
    )
    return queryset.annotate(
        withdrawal_count=Count("withdrawal_requests", distinct=True),
        pending_withdrawal_amount=Coalesce(
            Subquery(pending_total),
            Decimal("0.00"),
            output_field=DecimalField(max_digits=16, decimal_places=2),
        ),
    )


class DashboardView(APIView):
    def get(self, request):
        submissions = Submission.objects.filter(user=request.user)
        payload = {
            "balance": request.user.account.balance,
            "available_balance": available_balance(request.user),
            "active_request_count": PaymentRequest.objects.filter(
                status=PaymentRequest.Status.PUBLISHED,
            ).count(),
            "pending_submission_count": submissions.filter(
                status=Submission.Status.PENDING,
            ).count(),
            "accepted_submission_count": submissions.filter(
                status=Submission.Status.ACCEPTED,
            ).count(),
            "pending_withdrawal_count": WithdrawalRequest.objects.filter(
                user=request.user,
                status=WithdrawalRequest.Status.PENDING,
            ).count(),
            "recent_payment_requests": PaymentRequestSerializer(
                PaymentRequest.objects.filter(
                    status=PaymentRequest.Status.PUBLISHED,
                )[:5],
                many=True,
                context={"request": request},
            ).data,
            "recent_submissions": SubmissionSerializer(
                submissions.select_related("user__account", "payment_request")[:5],
                many=True,
                context={"request": request},
            ).data,
            "recent_balance_entries": BalanceEntrySerializer(
                BalanceEntry.objects.filter(user=request.user).select_related(
                    "user__account",
                    "submission",
                    "withdrawal",
                )[:5],
                many=True,
                context={"request": request},
            ).data,
        }
        return Response(payload)


class PaymentRequestListView(generics.ListAPIView):
    serializer_class = PaymentRequestSerializer

    def get_queryset(self):
        return PaymentRequest.objects.filter(status=PaymentRequest.Status.PUBLISHED)


class PaymentRequestDetailView(generics.RetrieveAPIView):
    serializer_class = PaymentRequestSerializer

    def get_queryset(self):
        return PaymentRequest.objects.filter(status=PaymentRequest.Status.PUBLISHED)


class SubmissionCreateView(generics.CreateAPIView):
    serializer_class = SubmissionCreateSerializer

    def post(self, request, *args, **kwargs):
        payment_request = get_object_or_404(
            PaymentRequest,
            pk=self.kwargs["pk"],
            status=PaymentRequest.Status.PUBLISHED,
        )
        serializer = self.get_serializer(
            data=request.data,
            context={
                **self.get_serializer_context(),
                "payment_request": payment_request,
            },
        )
        serializer.is_valid(raise_exception=True)
        submission = serializer.save()
        output = SubmissionSerializer(
            submission,
            context=self.get_serializer_context(),
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class MySubmissionListView(generics.ListAPIView):
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        return Submission.objects.filter(user=self.request.user).select_related(
            "user__account",
            "payment_request",
        )


class MySubmissionDetailView(generics.RetrieveAPIView):
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        return Submission.objects.filter(user=self.request.user).select_related(
            "user__account",
            "payment_request",
        )


class BalanceEntryListView(generics.ListAPIView):
    serializer_class = BalanceEntrySerializer

    def get_queryset(self):
        return BalanceEntry.objects.filter(user=self.request.user).select_related(
            "user__account",
            "submission",
        )


class PaymentRequestFileView(APIView):
    def get(self, request, pk):
        payment_request = get_object_or_404(PaymentRequest, pk=pk)
        if (
            not request.user.is_staff
            and payment_request.status != PaymentRequest.Status.PUBLISHED
        ):
            has_submission = Submission.objects.filter(
                user=request.user,
                payment_request=payment_request,
            ).exists()
            if not has_submission:
                raise Http404
        content_type = mimetypes.guess_type(payment_request.qr_image.name)[0]
        return FileResponse(
            payment_request.qr_image.open("rb"),
            content_type=content_type or "application/octet-stream",
        )


class SubmissionFileView(APIView):
    def get(self, request, pk):
        submission = get_object_or_404(Submission.objects.select_related("user"), pk=pk)
        if not request.user.is_staff and submission.user_id != request.user.id:
            raise Http404
        content_type = mimetypes.guess_type(submission.screenshot.name)[0]
        return FileResponse(
            submission.screenshot.open("rb"),
            content_type=content_type or "application/octet-stream",
        )


class AdminPaymentRequestListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminPaymentRequestSerializer

    def get_queryset(self):
        return PaymentRequest.objects.select_related("created_by__account").annotate(
            submission_count=Count("submissions")
        )


class AdminPaymentRequestDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminPaymentRequestSerializer
    queryset = PaymentRequest.objects.select_related("created_by__account").annotate(
        submission_count=Count("submissions")
    )

    def destroy(self, request, *args, **kwargs):
        payment_request = self.get_object()
        if payment_request.submissions.exists():
            return Response(
                {
                    "detail": (
                        "This payment request has submissions and cannot be deleted. "
                        "Close it instead."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )
        qr_image = payment_request.qr_image
        payment_request.delete()
        qr_image.delete(save=False)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminPaymentRequestForceDeleteView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def delete(self, request, pk):
        payment_request = get_object_or_404(PaymentRequest, pk=pk)
        confirmation = request.data.get("confirm_transaction_id")
        if confirmation != payment_request.transaction_id:
            return Response(
                {
                    "detail": (
                        "The transaction ID confirmation does not match this "
                        "payment request."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            force_delete_payment_request(payment_request_id=payment_request.id)
        except PaymentRequest.DoesNotExist:
            raise Http404 from None
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminSubmissionListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = SubmissionSerializer

    def get_queryset(self):
        queryset = Submission.objects.select_related(
            "user__account",
            "payment_request",
        )
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in Submission.Status.values:
                raise ValidationError({"status": "Invalid submission status."})
            queryset = queryset.filter(status=status_filter)

        user_id = self.request.query_params.get("user_id")
        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except ValueError as exc:
                raise ValidationError({"user_id": "Must be an integer."}) from exc

        payment_request_id = self.request.query_params.get("payment_request_id")
        if payment_request_id:
            try:
                queryset = queryset.filter(payment_request_id=int(payment_request_id))
            except ValueError as exc:
                raise ValidationError(
                    {"payment_request_id": "Must be an integer."}
                ) from exc
        return queryset


class AdminSubmissionDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = SubmissionSerializer
    queryset = Submission.objects.select_related("user__account", "payment_request")


class AdminSubmissionAcceptView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        get_object_or_404(Submission, pk=pk)
        serializer = SubmissionAcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = accept_submission(
                submission_id=pk,
                reviewer=request.user,
                final_amount=serializer.validated_data["final_amount"],
            )
        except Submission.DoesNotExist:
            raise Http404 from None
        except SubmissionAmountMismatchError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except SubmissionReviewError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = SubmissionSerializer(
            submission,
            context={"request": request},
        )
        return Response(serializer.data)


class AdminSubmissionDeclineView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        get_object_or_404(Submission, pk=pk)
        serializer = DeclineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            submission = decline_submission(
                submission_id=pk,
                reviewer=request.user,
                reason=serializer.validated_data["reason"],
            )
        except Submission.DoesNotExist:
            raise Http404 from None
        except SubmissionReviewError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output = SubmissionSerializer(
            submission,
            context={"request": request},
        )
        return Response(output.data)


class AdminUserListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUserSerializer

    def get_queryset(self):
        queryset = annotate_user_withdrawal_totals(
            User.objects.select_related("account").annotate(
                submission_count=Count("submissions", distinct=True),
            )
        )
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search),
            )
        return queryset.order_by("email")


class AdminUserDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminUserSerializer
    queryset = annotate_user_withdrawal_totals(
        User.objects.select_related("account").annotate(
            submission_count=Count("submissions", distinct=True),
        )
    )


class AdminBalanceEntryListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = BalanceEntrySerializer

    def get_queryset(self):
        queryset = BalanceEntry.objects.select_related(
            "user__account",
            "submission",
            "withdrawal",
        )
        user_id = self.request.query_params.get("user_id")
        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except ValueError as exc:
                raise ValidationError({"user_id": "Must be an integer."}) from exc
        return queryset


class WithdrawalBalanceView(APIView):
    def get(self, request):
        return Response(
            WithdrawalBalanceSerializer(withdrawal_balance_summary(request.user)).data
        )


class WithdrawalListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return WithdrawalCreateSerializer
        return WithdrawalRequestSerializer

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(
            user=self.request.user
        ).prefetch_related("payees")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(
            data=request.data,
            context={**self.get_serializer_context(), "seen_account_numbers": set()},
        )
        serializer.is_valid(raise_exception=True)
        withdrawal = serializer.save()
        output = WithdrawalRequestSerializer(
            withdrawal,
            context=self.get_serializer_context(),
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class WithdrawalDetailView(generics.RetrieveAPIView):
    serializer_class = WithdrawalRequestSerializer

    def get_queryset(self):
        return WithdrawalRequest.objects.filter(
            user=self.request.user
        ).prefetch_related("payees")


def apply_admin_withdrawal_filters(queryset, params):
    status_filter = params.get("status")
    if status_filter:
        if status_filter not in WithdrawalRequest.Status.values:
            raise ValidationError({"status": "Invalid withdrawal status."})
        queryset = queryset.filter(status=status_filter)

    user_id = params.get("user_id")
    if user_id:
        try:
            queryset = queryset.filter(user_id=int(user_id))
        except ValueError as exc:
            raise ValidationError({"user_id": "Must be an integer."}) from exc

    search = params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(reference__icontains=search)
            | Q(user__email__icontains=search)
            | Q(payees__payee_name__icontains=search)
            | Q(payees__account_number__icontains=search)
            | Q(payees__ifsc__icontains=search)
        ).distinct()
    return queryset


class AdminWithdrawalListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminWithdrawalRequestSerializer

    def get_queryset(self):
        queryset = WithdrawalRequest.objects.select_related(
            "user__account",
            "processed_by",
        ).prefetch_related("payees")
        return apply_admin_withdrawal_filters(queryset, self.request.query_params)


class AdminWithdrawalSummaryView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def get(self, request):
        queryset = apply_admin_withdrawal_filters(
            WithdrawalRequest.objects.all(), request.query_params
        )
        latest = (
            queryset.order_by("-created_at", "-id").values("id", "created_at").first()
        )
        summary = {
            "count": queryset.count(),
            "pending_count": queryset.filter(
                status=WithdrawalRequest.Status.PENDING
            ).count(),
            "latest_id": latest["id"] if latest else None,
            "latest_created_at": latest["created_at"] if latest else None,
            "latest_processed_at": queryset.aggregate(latest=Max("processed_at"))[
                "latest"
            ],
        }
        return Response(WithdrawalSummarySerializer(summary).data)


class AdminWithdrawalDetailView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminWithdrawalRequestSerializer
    queryset = WithdrawalRequest.objects.select_related(
        "user__account",
        "processed_by",
    ).prefetch_related("payees")


class AdminWithdrawalConfirmView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        get_object_or_404(WithdrawalRequest, pk=pk)
        serializer = WithdrawalConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = confirm_withdrawal(
                withdrawal_id=pk,
                reviewer=request.user,
                transaction_id=serializer.validated_data["transaction_id"],
                amount=serializer.validated_data["amount"],
            )
        except WithdrawalRequest.DoesNotExist:
            raise Http404 from None
        except (WithdrawalAmountMismatchError, WithdrawalBalanceError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except WithdrawalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output = AdminWithdrawalRequestSerializer(
            withdrawal,
            context={"request": request},
        )
        return Response(output.data)


class AdminWithdrawalRejectView(APIView):
    permission_classes = [permissions.IsAdminUser]

    def post(self, request, pk):
        get_object_or_404(WithdrawalRequest, pk=pk)
        serializer = WithdrawalRejectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdrawal = reject_withdrawal(
                withdrawal_id=pk,
                reviewer=request.user,
                reason=serializer.validated_data["reason"],
            )
        except WithdrawalRequest.DoesNotExist:
            raise Http404 from None
        except WithdrawalError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        output = AdminWithdrawalRequestSerializer(
            withdrawal,
            context={"request": request},
        )
        return Response(output.data)
