from django.urls import path

from .views import (
    AdminChatConversationListView,
    AdminChatMessageListCreateView,
    ChatMessageListCreateView,
    ChatSummaryView,
)

urlpatterns = [
    path("chat/", ChatSummaryView.as_view(), name="chat-summary"),
    path(
        "chat/messages/",
        ChatMessageListCreateView.as_view(),
        name="chat-message-list",
    ),
    path(
        "admin/chat/conversations/",
        AdminChatConversationListView.as_view(),
        name="admin-chat-conversation-list",
    ),
    path(
        "admin/chat/users/<int:user_id>/messages/",
        AdminChatMessageListCreateView.as_view(),
        name="admin-chat-message-list",
    ),
]
