from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserSerializer

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    sender = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields: tuple[str, ...] = (
            "id",
            "sender",
            "body",
            "created_at",
        )
        read_only_fields = fields

    def get_sender(self, obj):
        if obj.sender_id is None:
            return None
        return UserSerializer(obj.sender, context=self.context).data


class MessageCreateSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=2000)

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("A message is required.")
        return value


class ChatSummarySerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    last_message = serializers.SerializerMethodField()
    last_message_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = Conversation
        fields: tuple[str, ...] = (
            "message_count",
            "unread_count",
            "last_message",
            "last_message_at",
        )
        read_only_fields = fields

    def get_last_message(self, obj):
        message = obj.messages.order_by("-created_at").first()
        if message is None:
            return None
        return MessageSerializer(message, context=self.context).data


class AdminChatConversationSerializer(serializers.ModelSerializer):
    user = UserSerializer(source="*", read_only=True)
    message_count = serializers.IntegerField(read_only=True)
    unread_count = serializers.IntegerField(read_only=True)
    last_message_id = serializers.IntegerField(read_only=True)
    last_message_body = serializers.CharField(read_only=True)
    last_message_sender_id = serializers.IntegerField(read_only=True)
    last_message_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = User
        fields: tuple[str, ...] = (
            "user",
            "message_count",
            "unread_count",
            "last_message_id",
            "last_message_body",
            "last_message_sender_id",
            "last_message_at",
        )
        read_only_fields = fields
