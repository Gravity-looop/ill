from django.db import transaction

from .models import Conversation, Message


def get_or_create_conversation(user):
    conversation, _ = Conversation.objects.get_or_create(user=user)
    return conversation


@transaction.atomic
def send_message(*, conversation, sender, body):
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=body,
        is_read=False,
    )
    conversation.last_message_at = message.created_at
    conversation.save(update_fields=("last_message_at",))
    return message


@transaction.atomic
def mark_messages_read(*, conversation, reader):
    return (
        Message.objects.filter(conversation=conversation, is_read=False)
        .exclude(sender=reader)
        .update(is_read=True)
    )
