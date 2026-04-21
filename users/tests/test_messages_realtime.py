from datetime import date, timedelta

from allauth.socialaccount.models import SocialAccount
from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from communications.consumers import MessagesConsumer
from communications.models import ListingConversation
from communications.services import start_direct_conversation
from listings.models import RoommatePost

from .helpers import User


class MessagesRealtimeTests(TransactionTestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="owner",
            email="owner@bc.edu",
            password="test",
        )
        self.participant = User.objects.create_user(
            username="student",
            email="student@bc.edu",
            password="test",
        )
        self.outsider = User.objects.create_user(username="outsider", email="outsider@bc.edu", password="test")
        SocialAccount.objects.create(
            user=self.owner,
            provider="google",
            uid="google-owner",
            extra_data={"picture": "https://example.com/realtime-owner.png"},
        )
        self.listing = self.owner.listings.create(
            title="Realtime listing",
            address="140 Commonwealth Ave",
            price="1200.00",
            lease_type="FULL",
            start_date="2026-09-01",
            end_date="2027-05-31",
            approval_status="approved",
        )
        self.conversation = ListingConversation.objects.create(
            listing=self.listing,
            owner=self.owner,
            participant=self.participant,
        )

    def complete_roommate_profile(self, user):
        profile = user.student_profile
        profile.preferred_name = user.first_name or user.username
        profile.age = 21
        profile.gender = "female"
        profile.major = "Computer Science"
        profile.bio = "Quiet BC student looking for a good fit."
        profile.messy_level = 3
        profile.guest_level = 2
        profile.bedtime = 23
        profile.noise_level = 2
        profile.drink = 2
        profile.party = 2
        profile.save()
        user.profile_completed_at = timezone.now()
        user.save(update_fields=["profile_completed_at"])

    def create_roommate_post(self, author):
        if author.profile_completed_at is None:
            self.complete_roommate_profile(author)
        return RoommatePost.objects.create(
            author=author,
            title="Looking for one more roommate",
            description="Quiet BC student looking for a good fit for August.",
            housing_status=RoommatePost.HOUSING_NEED_HOME,
            current_group_size=1,
            open_spots=1,
            budget_min="1200",
            budget_max="1600",
            move_in_date=date.today() + timedelta(days=45),
            neighborhoods="Allston, Brighton",
            is_active=True,
        )

    def test_anonymous_socket_is_rejected(self):
        async def scenario():
            communicator = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_inactive_socket_is_rejected(self):
        self.participant.is_active = False
        self.participant.save(update_fields=["is_active"])

        async def scenario():
            communicator = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            communicator.scope["user"] = self.participant
            connected, close_code = await communicator.connect()
            self.assertFalse(connected)
            self.assertEqual(close_code, 4401)

        async_to_sync(scenario)()

    def test_participants_receive_realtime_message_event(self):
        self.owner.profile_image_url = "https://example.com/owner-avatar.jpg"
        self.owner.save(update_fields=["profile_image_url"])
        self.participant.profile_image_url = "https://example.com/student-avatar.jpg"
        self.participant.save(update_fields=["profile_image_url"])

        async def scenario():
            owner_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            owner_socket.scope["user"] = self.owner
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            owner_connected, _ = await owner_socket.connect()
            participant_connected, _ = await participant_socket.connect()
            self.assertTrue(owner_connected)
            self.assertTrue(participant_connected)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Is this still available?",
                }
            )

            owner_payload = await owner_socket.receive_json_from()
            participant_payload = await participant_socket.receive_json_from()

            self.assertEqual(owner_payload["type"], "message.created")
            self.assertEqual(participant_payload["type"], "message.created")
            self.assertEqual(owner_payload["message"]["body"], "Is this still available?")
            self.assertTrue(owner_payload["conversation"]["has_unread"])
            self.assertFalse(participant_payload["conversation"]["has_unread"])
            self.assertEqual(owner_payload["conversation"]["counterparty_role_label"], "Interested renter")
            self.assertEqual(participant_payload["conversation"]["counterparty_role_label"], "Listing owner")
            self.assertEqual(
                participant_payload["conversation"]["counterparty_avatar_url"], "https://example.com/realtime-owner.png"
            )
            self.assertEqual(owner_payload["conversation"]["listing_address"], self.listing.address)
            self.assertEqual(
                owner_payload["conversation"]["counterparty_avatar_url"], "https://example.com/student-avatar.jpg"
            )
            self.assertEqual(
                participant_payload["conversation"]["counterparty_avatar_url"], "https://example.com/realtime-owner.png"
            )
            self.assertEqual(owner_payload["message"]["sender_avatar_url"], "https://example.com/student-avatar.jpg")
            self.assertEqual(owner_payload["summary"]["conversation_delta"], 0)
            self.assertEqual(owner_payload["summary"]["unread_delta"], 1)
            self.assertEqual(participant_payload["summary"]["conversation_delta"], 0)
            self.assertEqual(participant_payload["summary"]["unread_delta"], 0)

            await owner_socket.disconnect()
            await participant_socket.disconnect()

        async_to_sync(scenario)()

    def test_sender_only_receives_client_message_id_echo(self):
        async def scenario():
            owner_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            owner_socket.scope["user"] = self.owner
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            owner_connected, _ = await owner_socket.connect()
            participant_connected, _ = await participant_socket.connect()
            self.assertTrue(owner_connected)
            self.assertTrue(participant_connected)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Ack this message.",
                    "client_message_id": "client-msg-123",
                }
            )

            owner_payload = await owner_socket.receive_json_from()
            participant_payload = await participant_socket.receive_json_from()

            self.assertEqual(owner_payload["type"], "message.created")
            self.assertEqual(participant_payload["type"], "message.created")
            self.assertNotIn("client_message_id", owner_payload["message"])
            self.assertEqual(participant_payload["message"]["client_message_id"], "client-msg-123")

            await owner_socket.disconnect()
            await participant_socket.disconnect()

        async_to_sync(scenario)()

    def test_direct_conversation_realtime_payload_uses_direct_context(self):
        self.complete_roommate_profile(self.owner)
        self.create_roommate_post(self.participant)
        self.direct_conversation, _, _ = start_direct_conversation(self.owner, self.participant, "Want to compare?")

        async def scenario():
            owner_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            owner_socket.scope["user"] = self.owner
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            owner_connected, _ = await owner_socket.connect()
            participant_connected, _ = await participant_socket.connect()
            self.assertTrue(owner_connected)
            self.assertTrue(participant_connected)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.direct_conversation.id,
                    "body": "Yes, let's compare budgets.",
                }
            )

            owner_payload = await owner_socket.receive_json_from()

            self.assertEqual(owner_payload["type"], "message.created")
            self.assertEqual(owner_payload["conversation"]["conversation_type"], "direct")
            self.assertEqual(owner_payload["conversation"]["context_title"], "Roommate chat")
            self.assertEqual(owner_payload["message"]["body"], "Yes, let's compare budgets.")

            await owner_socket.disconnect()
            await participant_socket.disconnect()

        async_to_sync(scenario)()

    def test_mark_read_sends_realtime_state_update(self):
        self.conversation.add_message(sender=self.participant, body="Is this still available?")

        async def scenario():
            owner_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            owner_socket.scope["user"] = self.owner

            connected, _ = await owner_socket.connect()
            self.assertTrue(connected)

            await owner_socket.send_json_to(
                {
                    "action": "mark_read",
                    "conversation_id": self.conversation.id,
                }
            )

            payload = await owner_socket.receive_json_from()
            self.assertEqual(payload["type"], "conversation.read")
            self.assertEqual(payload["conversation"]["id"], self.conversation.id)
            self.assertFalse(payload["conversation"]["has_unread"])
            self.assertEqual(payload["summary"]["conversation_delta"], 0)
            self.assertEqual(payload["summary"]["unread_delta"], -1)

            await owner_socket.disconnect()

        async_to_sync(scenario)()

    def test_non_participant_cannot_send_message(self):
        async def scenario():
            outsider_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            outsider_socket.scope["user"] = self.outsider

            connected, _ = await outsider_socket.connect()
            self.assertTrue(connected)

            await outsider_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Hello",
                }
            )
            payload = await outsider_socket.receive_json_from()

            self.assertEqual(payload["type"], "error")
            self.assertEqual(payload["message"], "Conversation not found.")

            await outsider_socket.disconnect()

        async_to_sync(scenario)()

    def test_blank_message_returns_validation_error(self):
        async def scenario():
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            connected, _ = await participant_socket.connect()
            self.assertTrue(connected)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "   ",
                }
            )
            payload = await participant_socket.receive_json_from()

            self.assertEqual(payload["type"], "error")
            self.assertEqual(payload["message"], "Enter a message before sending.")

            await participant_socket.disconnect()

        async_to_sync(scenario)()

    @override_settings(MESSAGE_SEND_RATE_LIMIT=1, MESSAGE_SEND_RATE_WINDOW_SECONDS=60)
    def test_websocket_message_rate_limit_returns_error(self):
        cache.clear()

        async def scenario():
            owner_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            owner_socket.scope["user"] = self.owner
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            owner_connected, _ = await owner_socket.connect()
            participant_connected, _ = await participant_socket.connect()
            self.assertTrue(owner_connected)
            self.assertTrue(participant_connected)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "First note",
                }
            )

            await owner_socket.receive_json_from()
            await participant_socket.receive_json_from()

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Second note",
                }
            )
            error_payload = await participant_socket.receive_json_from()

            self.assertEqual(error_payload["type"], "error")
            self.assertEqual(
                error_payload["message"], "Too many messages sent too quickly. Wait a minute and try again."
            )

            await owner_socket.disconnect()
            await participant_socket.disconnect()

        async_to_sync(scenario)()
        self.assertEqual(self.conversation.messages.count(), 1)

    def test_unsupported_action_returns_error(self):
        async def scenario():
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            connected, _ = await participant_socket.connect()
            self.assertTrue(connected)

            await participant_socket.send_json_to({"action": "ping"})
            payload = await participant_socket.receive_json_from()

            self.assertEqual(payload["type"], "error")
            self.assertEqual(payload["message"], "Unsupported websocket action.")

            await participant_socket.disconnect()

        async_to_sync(scenario)()

    def test_socket_closes_if_user_is_deactivated_after_connect(self):
        async def scenario():
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            connected, _ = await participant_socket.connect()
            self.assertTrue(connected)

            deactivate_participant = database_sync_to_async(
                self.participant.__class__._default_manager.filter(pk=self.participant.pk).update
            )
            await deactivate_participant(is_active=False)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Still here?",
                }
            )
            output = await participant_socket.receive_output()

            self.assertEqual(output["type"], "websocket.close")
            self.assertEqual(output["code"], 4401)

        async_to_sync(scenario)()

    def test_websocket_send_returns_error_when_counterparty_is_inactive(self):
        async def scenario():
            participant_socket = WebsocketCommunicator(MessagesConsumer.as_asgi(), "/ws/messages/")
            participant_socket.scope["user"] = self.participant

            connected, _ = await participant_socket.connect()
            self.assertTrue(connected)

            deactivate_owner = database_sync_to_async(
                self.owner.__class__._default_manager.filter(pk=self.owner.pk).update
            )
            await deactivate_owner(is_active=False)

            await participant_socket.send_json_to(
                {
                    "action": "send_message",
                    "conversation_id": self.conversation.id,
                    "body": "Still available?",
                }
            )
            payload = await participant_socket.receive_json_from()

            self.assertEqual(payload["type"], "error")
            self.assertEqual(
                payload["message"],
                "This conversation is read-only because one participant no longer has an active account.",
            )

            await participant_socket.disconnect()

        async_to_sync(scenario)()
