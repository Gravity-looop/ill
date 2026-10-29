from django.db.models import Count, F, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import User

from .models import Conversation, Message
from .serializers import (
    AdminChatConversationSerializer,
    ChatSummarySerializer,
    MessageCreateSerializer,
    MessageSerializer,
)
from .services import get_or_create_conversation, mark_messages_read, send_message


class ChatSummaryView(APIView):
    def get(self, request):
        conversation = get_or_create_conversation(request.user)
        summary = (
            Conversation.objects.filter(pk=conversation.pk)
            .annotate(
                message_count=Count("messages", distinct=True),
                unread_count=Count(
                    "messages",
                    filter=Q(
                        messages__is_read=False,
                        messages__sender__is_staff=True,
                    ),
                    distinct=True,
                ),
            )
            .get()
        )
        serializer = ChatSummarySerializer(summary, context={"request": request})
        return Response(serializer.data)


class ChatMessageListCreateView(generics.ListCreateAPIView):
    def get_serializer_class(self):
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_queryset(self):
        conversation = get_or_create_conversation(self.request.user)
        return conversation.messages.select_related("sender", "sender__account")

    def list(self, request, *args, **kwargs):
        mark_messages_read(
            conversation=get_or_create_conversation(request.user),
            reader=request.user,
        )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = send_message(
            conversation=get_or_create_conversation(request.user),
            sender=request.user,
            body=serializer.validated_data["body"],
        )
        output = MessageSerializer(
            message,
            context=self.get_serializer_context(),
        )
        return Response(output.data, status=status.HTTP_201_CREATED)


class AdminChatConversationListView(generics.ListAPIView):
    permission_classes = [permissions.IsAdminUser]
    serializer_class = AdminChatConversationSerializer

    def get_queryset(self):
        latest_message = Message.objects.filter(
            conversation__user_id=OuterRef("pk"),
        ).order_by("-created_at")
        queryset = User.objects.filter(is_staff=False).select_related("account")
        queryset = queryset.annotate(
            message_count=Count("conversation__messages", distinct=True),
            unread_count=Count(
                "conversation__messages",
                filter=Q(
                    conversation__messages__is_read=False,
                    conversation__messages__sender__is_staff=False,
                ),
                distinct=True,
            ),
            last_message_id=Subquery(latest_message.values("id")[:1]),
            last_message_body=Subquery(latest_message.values("body")[:1]),
            last_message_sender_id=Subquery(latest_message.values("sender_id")[:1]),
            last_message_at=Subquery(latest_message.values("created_at")[:1]),
        )
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(email__icontains=search)
                | Q(first_name__icontains=search)
                | Q(last_name__icontains=search),
            )
        return queryset.order_by(
            F("last_message_at").desc(nulls_last=True),
            "email",
        )


class AdminChatMessageListCreateView(generics.ListCreateAPIView):
    permission_classes = [permissions.IsAdminUser]

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MessageCreateSerializer
        return MessageSerializer

    def get_conversation_owner(self):
        return get_object_or_404(
            User.objects.filter(is_staff=False),
            pk=self.kwargs["user_id"],
        )

    def get_queryset(self):
        conversation = get_or_create_conversation(self.get_conversation_owner())
        return conversation.messages.select_related("sender", "sender__account")

    def list(self, request, *args, **kwargs):
        mark_messages_read(
            conversation=get_or_create_conversation(self.get_conversation_owner()),
            reader=request.user,
        )
        return super().list(request, *args, **kwargs)

    def create(self, request, *args, **kwargs):
        conversation = get_or_create_conversation(self.get_conversation_owner())
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message = send_message(
            conversation=conversation,
            sender=request.user,
            body=serializer.validated_data["body"],
        )
        output = MessageSerializer(
            message,
            context=self.get_serializer_context(),
        )
        return Response(output.data, status=status.HTTP_201_CREATED)
