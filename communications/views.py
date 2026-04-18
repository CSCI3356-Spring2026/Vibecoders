from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.utils import get_page, preserved_query_suffix
from users.selectors import pending_group_invite_for_conversation

from .forms import ConversationMessageForm
from .selectors import (
    accessible_conversations_for_user,
    conversation_summary_for_user,
    inbox_conversations_for_user,
)
from .services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    delete_conversation_for_user,
    mark_conversation_read,
    send_conversation_message,
    start_direct_conversation,
)

MESSAGES_PER_PAGE = 12
THREAD_MESSAGES_PER_PAGE = 50


def _accessible_conversation_or_404(user, conversation_id):
    return get_object_or_404(accessible_conversations_for_user(user), id=conversation_id)


def _decorate_conversation_for_user(conversation, user):
    if conversation is None:
        return None
    conversation.ui_counterparty = conversation.counterparty_for(user)
    conversation.ui_counterparty_name = conversation.ui_counterparty.display_name
    conversation.ui_counterparty_role_label = conversation.counterparty_role_label_for(user)
    conversation.ui_has_unread = conversation.has_unread_for(user)
    conversation.ui_listing_image = conversation.listing.primary_image if conversation.listing_id else None
    conversation.ui_context_title = conversation.context_title_for(user)
    conversation.ui_context_subtitle = conversation.context_subtitle_for(user)
    conversation.ui_context_meta = conversation.context_meta_for(user)
    return conversation


def _decorate_conversations_for_user(conversations, user):
    return [_decorate_conversation_for_user(conversation, user) for conversation in conversations]


def _conversation_rows(conversations_page, selected_conversation):
    rows = list(conversations_page.object_list)
    if selected_conversation and all(conversation.id != selected_conversation.id for conversation in rows):
        rows.insert(0, selected_conversation)
    return rows


@login_required
def messages_inbox(request, conversation_id=None):
    conversations_qs = inbox_conversations_for_user(request.user)
    conversations_page = get_page(conversations_qs, request.GET.get("page"), MESSAGES_PER_PAGE)
    _decorate_conversations_for_user(conversations_page.object_list, request.user)

    selected_conversation = None
    if conversation_id:
        selected_conversation = get_object_or_404(conversations_qs, id=conversation_id)
    else:
        first_conversation = conversations_page.object_list.first()
        if first_conversation:
            selected_conversation = first_conversation

    if selected_conversation:
        mark_conversation_read(selected_conversation, request.user)
        _decorate_conversation_for_user(selected_conversation, request.user)
        selected_conversation.ui_has_unread = False
        for conversation in conversations_page.object_list:
            if conversation.id == selected_conversation.id:
                conversation.ui_has_unread = False

    reply_placeholder = "Ask about timing, availability, rent, or next steps."
    if selected_conversation and selected_conversation.is_direct:
        reply_placeholder = "Introduce yourself, compare housing plans, or talk next steps."
    reply_form = ConversationMessageForm(placeholder=reply_placeholder)

    conversation_rows = _conversation_rows(conversations_page, selected_conversation)
    thread_messages = []
    thread_messages_page = None
    thread_pagination_query = ""
    pending_group_invite = None
    if selected_conversation:
        pending_group_invite = pending_group_invite_for_conversation(request.user, selected_conversation)
        messages_qs = (
            selected_conversation.messages.select_related("sender")
            .prefetch_related("sender__socialaccount_set")
            .order_by("-created_at")
        )
        thread_messages_page = get_page(messages_qs, request.GET.get("thread_page"), THREAD_MESSAGES_PER_PAGE)
        thread_messages = list(reversed(list(thread_messages_page.object_list)))
        thread_pagination_query = preserved_query_suffix(request.GET, "thread_page")

    context = {
        **conversation_summary_for_user(request.user),
        "conversations": conversations_page,
        "conversation_rows": conversation_rows,
        "conversations_total": conversations_page.paginator.count,
        "pagination_query": preserved_query_suffix(request.GET, "page"),
        "selected_conversation": selected_conversation,
        "thread_messages": thread_messages,
        "thread_messages_page": thread_messages_page,
        "thread_pagination_query": thread_pagination_query,
        "reply_form": reply_form,
        "reply_max_length": reply_form.fields["body"].max_length,
        "pending_group_invite": pending_group_invite,
    }
    return render(request, "communications/messages.html", context)


@login_required
@require_POST
def reply_conversation(request, conversation_id):
    conversation = _accessible_conversation_or_404(request.user, conversation_id)
    if not consume_message_send_rate_limit(request.user):
        messages.error(request, MESSAGE_SEND_RATE_LIMIT_ERROR)
        return redirect("communications:detail", conversation_id=conversation.pk)
    form = ConversationMessageForm(request.POST)
    if form.is_valid():
        try:
            send_conversation_message(conversation, request.user, form.cleaned_data["body"])
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                message = next(iter(exc.message_dict.values()))[0]
            else:
                message = exc.messages[0]
            messages.error(request, message)
        else:
            messages.success(request, "Reply sent.")
    else:
        messages.error(request, "Enter a message before sending.")

    return redirect("communications:detail", conversation_id=conversation.pk)


@login_required
@require_POST
def start_direct_conversation_view(request, user_id):
    recipient = get_object_or_404(get_user_model()._default_manager.select_related("student_profile"), id=user_id)
    if not consume_message_send_rate_limit(request.user):
        messages.error(request, MESSAGE_SEND_RATE_LIMIT_ERROR)
        return redirect("users:public_profile", user_id=recipient.pk)

    form = ConversationMessageForm(
        request.POST,
        placeholder="Introduce yourself, compare housing plans, or talk next steps.",
    )
    if form.is_valid():
        try:
            conversation, _, created = start_direct_conversation(request.user, recipient, form.cleaned_data["body"])
        except ValidationError as exc:
            if hasattr(exc, "message_dict"):
                message = next(iter(exc.message_dict.values()))[0]
            else:
                message = exc.messages[0]
            messages.error(request, message)
        else:
            messages.success(request, "Conversation started." if created else "Message sent.")
            return redirect("communications:detail", conversation_id=conversation.pk)
    else:
        messages.error(request, "Enter a message before sending.")

    return redirect(f"{reverse('users:public_profile', args=[recipient.pk])}#message-user")


@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conversation = _accessible_conversation_or_404(request.user, conversation_id)
    delete_conversation_for_user(conversation, request.user)
    messages.success(request, "Conversation deleted.")
    return redirect("communications:messages")
