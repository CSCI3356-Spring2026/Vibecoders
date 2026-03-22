import { createConversationListController } from "./messages_list.js";
import { buildUserAvatar } from "./messages_avatar.js";

export function createMessagesUi(root) {
    const conversationUrlTemplate = root.dataset.conversationUrlTemplate || "";
    const currentUserId = Number(root.dataset.currentUserId || 0);
    const selectedConversationId = Number(root.dataset.selectedConversationId || 0);
    const currentThreadPage = Number(root.dataset.threadPage || 1);
    const errorContainer = root.querySelector("[data-message-errors]");
    const totalCountChips = root.querySelectorAll("[data-total-conversations]");
    const unreadCountChip = root.querySelector("[data-unread-count]");
    const connectionChips = root.querySelectorAll("[data-message-connection]");
    const deliveryState = root.querySelector("[data-message-delivery-state]");
    const threadMessageCount = root.querySelector("[data-thread-message-count]");
    const threadLastUpdated = root.querySelector("[data-thread-last-updated]");
    const conversationList = root.querySelector("[data-conversation-list]");
    const messageThread = root.querySelector("[data-message-thread]");
    const replyForm = root.querySelector("[data-reply-form]");
    const replyInput = replyForm?.querySelector("textarea");
    const replySubmit = replyForm?.querySelector("[data-message-submit]");
    const characterCount = root.querySelector("[data-message-count]");
    let totalConversations = Number(root.dataset.totalConversationsCount || 0);
    let unreadConversations = Number(root.dataset.totalUnreadCount || 0);

    const conversationUrl = (conversationId) => {
        if (!conversationUrlTemplate.includes("/0/")) {
            return "#";
        }
        return conversationUrlTemplate.replace("/0/", `/${conversationId}/`);
    };
    const conversationListController = createConversationListController({
        conversationList,
        conversationUrl,
        selectedConversationId,
    });

    const formatLongDate = (isoString) =>
        new Date(isoString).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });

    const formatThreadDate = (isoString) =>
        new Date(isoString).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
        });

    const showError = (message) => {
        if (!errorContainer) {
            return;
        }
        errorContainer.innerHTML = "";
        const alert = document.createElement("div");
        alert.className = "alert alert-danger mb-0";
        alert.role = "alert";
        alert.textContent = message;
        errorContainer.appendChild(alert);
    };

    const clearError = () => {
        if (errorContainer) {
            errorContainer.innerHTML = "";
        }
    };

    const renderTotalConversationCount = () => {
        totalCountChips.forEach((chip) => {
            chip.textContent =
                chip.dataset.totalConversations === "sidebar"
                    ? `${totalConversations} total`
                    : `${totalConversations} conversation${totalConversations === 1 ? "" : "s"}`;
        });
    };

    const renderUnreadCount = () => {
        if (unreadCountChip) {
            unreadCountChip.textContent = `${Math.max(0, unreadConversations)} unread`;
        }
    };

    const applySummaryDelta = (summary) => {
        if (!summary) {
            return;
        }

        totalConversations = Math.max(0, totalConversations + Number(summary.conversation_delta || 0));
        unreadConversations = Math.max(0, unreadConversations + Number(summary.unread_delta || 0));
        renderTotalConversationCount();
        renderUnreadCount();
    };

    const setConnectionState = (state) => {
        const config = {
            connecting: {
                chipText: "Connecting…",
                deliveryText: "Connecting live updates…",
                className: "is-connecting",
            },
            live: {
                chipText: "Live",
                deliveryText: "Live updates on.",
                className: "is-live",
            },
            reconnecting: {
                chipText: "Reconnecting…",
                deliveryText: "Reconnecting. Send still works.",
                className: "is-reconnecting",
            },
            offline: {
                chipText: "Reconnect required",
                deliveryText: "Realtime offline. Page refresh fallback.",
                className: "is-offline",
            },
        }[state];

        if (!config) {
            return;
        }

        connectionChips.forEach((chip) => {
            chip.classList.remove("is-connecting", "is-live", "is-reconnecting", "is-offline");
            chip.classList.add(config.className);
            chip.textContent = config.chipText;
        });

        if (deliveryState) {
            deliveryState.textContent = config.deliveryText;
        }
    };

    const updateComposeState = () => {
        if (!replyInput) {
            return;
        }

        const rawLength = replyInput.value.length;
        const trimmedLength = replyInput.value.trim().length;

        if (characterCount) {
            const maxLength = replyInput.maxLength > 0 ? replyInput.maxLength : 0;
            characterCount.textContent = maxLength ? `${rawLength} / ${maxLength}` : `${rawLength}`;
        }

        if (replySubmit) {
            replySubmit.disabled = trimmedLength === 0;
        }
    };

    const threadIsNearBottom = () => {
        if (!messageThread) {
            return true;
        }
        const remainingScroll = messageThread.scrollHeight - messageThread.clientHeight - messageThread.scrollTop;
        return remainingScroll < 48;
    };

    const appendMessageBubble = (message) => {
        if (!messageThread) {
            return;
        }
        if (messageThread.querySelector(`[data-message-id="${message.id}"]`)) {
            return;
        }

        const shouldStickToBottom = message.sender_id === currentUserId || threadIsNearBottom();

        const row = document.createElement("div");
        row.className = "message-row";
        row.dataset.messageId = String(message.id);
        row.classList.add(message.sender_id === currentUserId ? "is-outbound" : "is-inbound");

        const avatar = buildUserAvatar({
            name: message.sender_name,
            imageUrl: message.sender_avatar_url,
            sizeClass: "user-avatar-sm",
            extraClass: "message-avatar",
        });

        const stack = document.createElement("div");
        stack.className = "message-bubble-stack";

        const meta = document.createElement("div");
        meta.className = "message-bubble-meta";

        const sender = document.createElement("span");
        sender.className = "message-sender-name";
        sender.textContent = message.sender_id === currentUserId ? "You" : message.sender_name;
        meta.appendChild(sender);

        const timestamp = document.createElement("span");
        timestamp.className = "message-timestamp";
        timestamp.textContent = formatLongDate(message.created_at);
        meta.appendChild(timestamp);

        const body = document.createElement("div");
        body.className = "message-bubble-body";
        body.textContent = message.body;

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.classList.add(message.sender_id === currentUserId ? "is-outbound" : "is-inbound");
        bubble.appendChild(body);

        stack.appendChild(meta);
        stack.appendChild(bubble);
        row.appendChild(avatar);
        row.appendChild(stack);
        messageThread.appendChild(row);

        if (shouldStickToBottom) {
            messageThread.scrollTop = messageThread.scrollHeight;
        }

        if (threadMessageCount) {
            const nextCount = Number(threadMessageCount.dataset.threadMessageCount || 0) + 1;
            threadMessageCount.dataset.threadMessageCount = String(nextCount);
            threadMessageCount.textContent = `${nextCount} message${nextCount === 1 ? "" : "s"}`;
        }

        if (threadLastUpdated) {
            threadLastUpdated.textContent = `Updated ${formatThreadDate(message.created_at)}`;
        }
    };

    const handleConversationRead = (payload) => {
        applySummaryDelta(payload.summary);
        const item = conversationList?.querySelector(`[data-conversation-id="${payload.conversation.id}"]`);
        if (item) {
            conversationListController.update(item, payload.conversation);
        }
    };

    const handleMessageCreated = (payload, options = {}) => {
        clearError();
        applySummaryDelta(payload.summary);
        conversationListController.upsert(payload.conversation);

        if (payload.conversation.id !== selectedConversationId) {
            return;
        }

        if (currentThreadPage === 1) {
            appendMessageBubble(payload.message);

            if (payload.message.sender_id !== currentUserId) {
                options.onSelectedInboundMessage?.();
                const activeItem = conversationList?.querySelector(
                    `[data-conversation-id="${selectedConversationId}"]`
                );
                conversationListController.markUnread(activeItem, false);
            }
            return;
        }

        if (deliveryState) {
            deliveryState.textContent = "Newer messages are available on the latest page.";
        }
    };

    const getReplyBody = () => replyInput?.value.trim() || "";

    const clearReplyInput = () => {
        if (!replyInput) {
            return;
        }
        replyInput.value = "";
        updateComposeState();
    };

    return {
        websocketPath: root.dataset.websocketPath || "",
        currentUserId,
        selectedConversationId,
        currentThreadPage,
        replyForm,
        replyInput,
        init() {
            renderTotalConversationCount();
            renderUnreadCount();
            updateComposeState();
        },
        showError,
        clearError,
        setConnectionState,
        updateComposeState,
        handleConversationRead,
        handleMessageCreated,
        getReplyBody,
        clearReplyInput,
    };
}
