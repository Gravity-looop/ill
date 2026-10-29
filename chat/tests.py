from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User

from .models import Conversation, Message


class ChatApiTests(APITestCase):
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

    def send_message(self, body="Hello admin", client=None):
        client = client or self.client
        return client.post(
            reverse("chat-message-list"),
            {"body": body},
            format="json",
        )

    def read_thread(self, client=None, user_id=None):
        client = client or self.client
        if user_id is None:
            return client.get(reverse("chat-message-list"))
        return client.get(
            reverse("admin-chat-message-list", kwargs={"user_id": user_id})
        )

    def inbox(self, client=None, **params):
        client = client or self.admin_client
        return client.get(reverse("admin-chat-conversation-list"), params)

    def summary(self, client=None):
        client = client or self.client
        return client.get(reverse("chat-summary"))

    def test_chat_requires_authentication(self):
        anonymous = self.client_class()

        response = anonymous.get(reverse("chat-message-list"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_send_a_message_and_read_the_thread(self):
        response = self.send_message("My payment screenshot is unclear.")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["body"], "My payment screenshot is unclear.")
        self.assertEqual(response.data["sender"]["email"], self.user.email)
        self.assertNotIn("is_read", response.data)

        conversation = Conversation.objects.get(user=self.user)
        self.assertEqual(conversation.messages.count(), 1)
        self.assertIsNotNone(conversation.last_message_at)

        thread = self.read_thread()

        self.assertEqual(thread.status_code, status.HTTP_200_OK)
        self.assertEqual(thread.data["count"], 1)
        self.assertEqual(thread.data["results"][0]["body"], response.data["body"])

    def test_admin_reply_is_visible_to_the_user(self):
        self.send_message("Please review my submission.")

        response = self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.user.id}),
            {"body": "We are reviewing it now."},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["sender"]["email"], self.admin.email)

        thread = self.read_thread()

        self.assertEqual(thread.data["count"], 2)
        self.assertEqual(
            [message["body"] for message in thread.data["results"]],
            ["Please review my submission.", "We are reviewing it now."],
        )

    def test_user_cannot_read_another_users_thread(self):
        self.send_message("Private message.")

        self.authenticate(self.other_user)
        thread = self.read_thread()

        self.assertEqual(thread.status_code, status.HTTP_200_OK)
        self.assertEqual(thread.data["count"], 0)
        self.assertEqual(thread.data["results"], [])

    def test_user_messages_stay_in_the_senders_own_thread(self):
        self.authenticate(self.other_user)
        self.send_message("Message from the other account.")

        self.authenticate(self.user)

        self.assertEqual(self.read_thread().data["count"], 0)
        conversation = Conversation.objects.get(user=self.other_user)
        self.assertEqual(conversation.messages.count(), 1)

    def test_user_message_is_read_and_admin_message_is_unread_until_opened(self):
        self.send_message("First message from the user.")
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.user.id}),
            {"body": "Admin reply"},
            format="json",
        )

        self.assertEqual(self.summary().data["unread_count"], 1)

        self.read_thread()

        self.assertEqual(self.summary().data["unread_count"], 0)
        self.assertTrue(
            Message.objects.get(
                conversation__user=self.user,
                body="Admin reply",
            ).is_read
        )

    def test_opening_the_thread_as_admin_does_not_clear_the_user_unread_count(self):
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.user.id}),
            {"body": "Admin reply"},
            format="json",
        )

        self.read_thread(client=self.admin_client, user_id=self.user.id)

        self.assertEqual(self.summary().data["unread_count"], 1)

    def test_own_messages_are_never_unread_for_their_sender(self):
        self.send_message("Message from the user")
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.user.id}),
            {"body": "Admin reply"},
            format="json",
        )

        summary = self.summary()
        inbox = self.inbox()

        self.assertEqual(summary.data["message_count"], 2)
        self.assertEqual(summary.data["unread_count"], 1)
        self.assertEqual(inbox.data["results"][0]["message_count"], 2)
        self.assertEqual(inbox.data["results"][0]["unread_count"], 1)

    def test_summary_reports_counts_and_last_message(self):
        empty = self.summary()

        self.assertEqual(empty.status_code, status.HTTP_200_OK)
        self.assertEqual(empty.data["message_count"], 0)
        self.assertEqual(empty.data["unread_count"], 0)
        self.assertIsNone(empty.data["last_message"])
        self.assertIsNone(empty.data["last_message_at"])
        self.assertTrue(Conversation.objects.filter(user=self.user).exists())

        self.send_message("First message from the user.")
        self.send_message("Second message from the user.")
        populated = self.summary()

        self.assertEqual(populated.data["message_count"], 2)
        self.assertEqual(
            populated.data["last_message"]["body"], "Second message from the user."
        )
        self.assertIsNotNone(populated.data["last_message_at"])

    def test_inbox_lists_users_with_counts_and_excludes_staff(self):
        self.send_message("Hello admin")
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.other_user.id}),
            {"body": "Unread admin reply"},
            format="json",
        )

        response = self.inbox()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 2)
        rows = {row["user"]["email"]: row for row in response.data["results"]}
        self.assertEqual(set(rows), {"user@example.com", "other@example.com"})
        self.assertNotIn("admin@example.com", rows)

        sender_row = rows["user@example.com"]
        self.assertEqual(sender_row["message_count"], 1)
        self.assertEqual(sender_row["unread_count"], 1)
        self.assertEqual(sender_row["last_message_body"], "Hello admin")
        self.assertEqual(sender_row["last_message_sender_id"], self.user.id)

        other_row = rows["other@example.com"]
        self.assertEqual(other_row["message_count"], 1)
        self.assertEqual(other_row["unread_count"], 0)
        self.assertEqual(other_row["last_message_sender_id"], self.admin.id)

    def test_inbox_orders_the_most_recent_thread_first(self):
        self.send_message("Older message")
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.other_user.id}),
            {"body": "Newer message"},
            format="json",
        )

        response = self.inbox()

        self.assertEqual(
            [row["user"]["email"] for row in response.data["results"]],
            ["other@example.com", "user@example.com"],
        )

    def test_inbox_places_users_without_messages_last(self):
        self.send_message("Only thread with messages")

        response = self.inbox()

        self.assertEqual(
            [row["user"]["email"] for row in response.data["results"]],
            ["user@example.com", "other@example.com"],
        )
        self.assertIsNone(response.data["results"][1]["last_message_id"])
        self.assertIsNone(response.data["results"][1]["last_message_body"])
        self.assertEqual(response.data["results"][1]["message_count"], 0)

    def test_inbox_search_filters_users(self):
        response = self.inbox(search="other@")

        self.assertEqual(response.data["count"], 1)
        self.assertEqual(
            response.data["results"][0]["user"]["email"],
            "other@example.com",
        )

    def test_admin_can_open_the_thread_of_a_user_who_never_wrote(self):
        response = self.read_thread(
            client=self.admin_client, user_id=self.other_user.id
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)

    def test_admin_opening_a_thread_marks_user_messages_read(self):
        self.send_message("Please review this")

        self.assertEqual(
            self.inbox().data["results"][0]["unread_count"],
            1,
        )

        self.read_thread(client=self.admin_client, user_id=self.user.id)

        self.assertEqual(
            self.inbox().data["results"][0]["unread_count"],
            0,
        )

    def test_admin_cannot_message_another_admin(self):
        response = self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.admin.id}),
            {"body": "Hello colleague"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(Conversation.objects.filter(user=self.admin).exists())

    def test_normal_user_cannot_access_admin_chat(self):
        inbox_response = self.inbox(client=self.client)
        thread_response = self.read_thread(
            client=self.client, user_id=self.other_user.id
        )
        post_response = self.client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.other_user.id}),
            {"body": "Let me in"},
            format="json",
        )

        self.assertEqual(inbox_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(thread_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(post_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_blank_message_is_rejected(self):
        response = self.send_message("   ")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("body", response.data)
        self.assertEqual(Message.objects.count(), 0)

    def test_message_over_two_thousand_characters_is_rejected(self):
        response = self.send_message("a" * 2001)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("body", response.data)
        self.assertEqual(Message.objects.count(), 0)

    def test_message_is_trimmed(self):
        response = self.send_message("  Padded message  ")

        self.assertEqual(response.data["body"], "Padded message")

    def test_message_list_is_paginated(self):
        conversation = Conversation.objects.create(user=self.user)
        Message.objects.bulk_create(
            [
                Message(
                    conversation=conversation,
                    sender=self.user,
                    body=f"Message {index}",
                    is_read=True,
                )
                for index in range(21)
            ]
        )

        response = self.read_thread()

        self.assertEqual(response.data["count"], 21)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])

    def test_deleted_sender_is_reported_as_null(self):
        self.admin_client.post(
            reverse("admin-chat-message-list", kwargs={"user_id": self.user.id}),
            {"body": "Message from a removed admin"},
            format="json",
        )
        self.admin.delete()

        thread = self.read_thread()

        self.assertEqual(thread.data["count"], 1)
        self.assertIsNone(thread.data["results"][0]["sender"])
        self.assertEqual(
            thread.data["results"][0]["body"], "Message from a removed admin"
        )
