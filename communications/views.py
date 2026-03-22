from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.utils import get_page, preserved_query_suffix

from .forms import ConversationMessageForm
from .selectors import accessible_conversations_for_user, conversation_summary_for_user, inbox_conversations_for_user
from .services import (
    MESSAGE_SEND_RATE_LIMIT_ERROR,
    consume_message_send_rate_limit,
    delete_conversation_for_user,
    mark_conversation_read,
    send_listing_message,
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
    conversation.ui_listing_image = conversation.listing.primary_image
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
    reply_form = ConversationMessageForm()

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

    conversation_rows = _conversation_rows(conversations_page, selected_conversation)
    thread_messages = []
    thread_messages_page = None
    thread_pagination_query = ""
    if selected_conversation:
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
        send_listing_message(conversation, request.user, form.cleaned_data["body"])
        messages.success(request, "Reply sent.")
    else:
        messages.error(request, "Enter a message before sending.")

    return redirect("communications:detail", conversation_id=conversation.pk)


@login_required
@require_POST
def delete_conversation(request, conversation_id):
    conversation = _accessible_conversation_or_404(request.user, conversation_id)
    delete_conversation_for_user(conversation, request.user)
    messages.success(request, "Conversation deleted.")
    return redirect("communications:messages")
