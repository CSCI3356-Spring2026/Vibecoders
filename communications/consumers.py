from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.core.exceptions import ValidationError

from .models import ListingConversation
from .services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    mark_conversation_read,
    send_conversation_message,
    user_messages_group_name,
)


class MessagesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = self.scope.get("user")
        if not self.user or self.user.is_anonymous or not self.user.is_active:
            await self.close(code=4401)
            return

        self.user_group_name = user_messages_group_name(self.user.id)
        await self.channel_layer.group_add(self.user_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, "user_group_name"):
            await self.channel_layer.group_discard(self.user_group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if not await self._user_is_active():
            await self.close(code=4401)
            return

        action = (content.get("action") or "").strip()
        if action == "send_message":
            await self._handle_send_message(content)
            return
        if action == "mark_read":
            await self._handle_mark_read(content)
            return
        await self.send_json({"type": "error", "message": "Unsupported websocket action."})

    async def message_event(self, event):
        payload = {
            "type": event["event"],
            "conversation": event["conversation"],
        }
        if "message" in event:
            payload["message"] = event["message"]
        if "summary" in event:
            payload["summary"] = event["summary"]
        await self.send_json(payload)

    async def _handle_send_message(self, content):
        conversation_id = content.get("conversation_id")
        if not isinstance(conversation_id, int):
            await self.send_json({"type": "error", "message": "A valid conversation id is required."})
            return
        if not await self._consume_send_rate_limit():
            await self.send_json({"type": "error", "message": MESSAGE_SEND_RATE_LIMIT_ERROR})
            return

        body = content.get("body", "")
        try:
            sent = await self._send_message(conversation_id, body)
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                message = exc.message_dict.get("body", exc.messages)[0]
            else:
                message = exc.messages[0]
            await self.send_json({"type": "error", "message": message})
            return

        if not sent:
            await self.send_json({"type": "error", "message": "Conversation not found."})

    async def _handle_mark_read(self, content):
        conversation_id = content.get("conversation_id")
        if not isinstance(conversation_id, int):
            await self.send_json({"type": "error", "message": "A valid conversation id is required."})
            return

        marked = await self._mark_read(conversation_id)
        if not marked:
            await self.send_json({"type": "error", "message": "Conversation not found."})

    @database_sync_to_async
    def _send_message(self, conversation_id, body):
        conversation = ListingConversation.objects.visible_to(self.user).only("id").filter(id=conversation_id).first()
        if conversation is None:
            return False
        send_conversation_message(conversation, self.user, body)
        return True

    @database_sync_to_async
    def _mark_read(self, conversation_id):
        conversation = ListingConversation.objects.visible_to(self.user).only("id").filter(id=conversation_id).first()
        if conversation is None:
            return False
        mark_conversation_read(conversation, self.user)
        return True

    @database_sync_to_async
    def _user_is_active(self):
        return self.user.__class__._default_manager.filter(pk=self.user.pk, is_active=True).exists()

    @sync_to_async
    def _consume_send_rate_limit(self):
        return consume_message_send_rate_limit(self.user)
