(function () {
    const root = document.querySelector("[data-messages-root]");
    if (!root) {
        return;
    }

    const websocketPath = root.dataset.websocketPath;
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
    let socket = null;
    let reconnectAttempts = 0;
    let reconnectTimerId = null;
    let isShuttingDown = false;
    let totalConversations = Number(root.dataset.totalConversationsCount || 0);
    let unreadConversations = Number(root.dataset.totalUnreadCount || 0);
    const stopReconnectCodes = new Set([4401, 4403, 1008]);

    if (!websocketPath) {
        return;
    }

    const websocketProtocol = window.location.protocol === "https:" ? "wss" : "ws";

    const conversationUrl = (conversationId) => {
        if (!conversationUrlTemplate.includes("/0/")) {
            return "#";
        }
        return conversationUrlTemplate.replace("/0/", `/${conversationId}/`);
    };

    const formatShortDate = (isoString) =>
        new Date(isoString).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
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

    const initialFromName = (name) => {
        const trimmed = (name || "").trim();
        return trimmed ? trimmed.charAt(0).toUpperCase() : "?";
    };

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

    const appendConversationMedia = (container, conversation) => {
        if (!container) {
            return;
        }
        container.innerHTML = "";

        if (conversation.listing_image_url) {
            const image = document.createElement("img");
            image.src = conversation.listing_image_url;
            image.alt = conversation.listing_title;
            container.appendChild(image);
            return;
        }

        const fallback = document.createElement("span");
        fallback.className = "messages-list-avatar";
        fallback.setAttribute("aria-hidden", "true");
        fallback.textContent = initialFromName(conversation.counterparty_name);
        container.appendChild(fallback);
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

        const bubble = document.createElement("div");
        bubble.className = "message-bubble";
        bubble.dataset.messageId = String(message.id);
        bubble.classList.add(message.sender_id === currentUserId ? "is-outbound" : "is-inbound");

        const meta = document.createElement("div");
        meta.className = "message-bubble-meta";

        const sender = document.createElement("span");
        sender.textContent = message.sender_name;
        meta.appendChild(sender);

        const timestamp = document.createElement("span");
        timestamp.textContent = formatLongDate(message.created_at);
        meta.appendChild(timestamp);

        const body = document.createElement("div");
        body.className = "message-bubble-body";
        body.textContent = message.body;

        bubble.appendChild(meta);
        bubble.appendChild(body);
        messageThread.appendChild(bubble);
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

    const ensureUnreadDot = (item, hasUnread) => {
        if (!item) {
            return false;
        }

        const existingDot = item.querySelector("[data-role='conversation-unread']");
        const hadUnread = Boolean(existingDot);

        if (hasUnread) {
            if (!existingDot) {
                const dot = document.createElement("span");
                dot.className = "messages-unread-dot";
                dot.setAttribute("aria-label", "Unread conversation");
                dot.dataset.role = "conversation-unread";
                item.querySelector(".messages-list-topline-side")?.appendChild(dot);
            }
        } else if (existingDot) {
            existingDot.remove();
        }

        return hadUnread;
    };

    const buildConversationItem = (conversation) => {
        const item = document.createElement("a");
        item.className = "messages-list-item";
        item.dataset.conversationId = String(conversation.id);
        item.href = conversationUrl(conversation.id);
        if (conversation.id === selectedConversationId) {
            item.classList.add("is-active");
        }

        item.innerHTML = `
            <div class="messages-list-row">
                <div class="messages-list-media" data-role="conversation-media"></div>
                <div class="messages-list-main">
                    <div class="messages-list-topline">
                        <span class="messages-list-name" data-role="conversation-name"></span>
                        <div class="messages-list-topline-side">
                            <span class="messages-list-date" data-role="conversation-date"></span>
                        </div>
                    </div>
                    <div class="messages-list-subject" data-role="conversation-subject"></div>
                    <div class="messages-list-preview" data-role="conversation-preview"></div>
                </div>
            </div>
        `;

        updateConversationItem(item, conversation);
        return item;
    };

    const updateConversationItem = (item, conversation) => {
        item.querySelector("[data-role='conversation-name']").textContent = conversation.counterparty_name;
        item.querySelector("[data-role='conversation-date']").textContent = formatShortDate(conversation.last_message_at);
        item.querySelector("[data-role='conversation-subject']").textContent = conversation.listing_title;
        item.querySelector("[data-role='conversation-preview']").textContent =
            conversation.last_message_preview || "No messages yet.";
        appendConversationMedia(item.querySelector("[data-role='conversation-media']"), conversation);
        ensureUnreadDot(item, Boolean(conversation.has_unread));
    };

    const upsertConversation = (conversation) => {
        if (!conversationList) {
            return;
        }

        let item = conversationList.querySelector(`[data-conversation-id="${conversation.id}"]`);
        const existed = Boolean(item);

        if (!item) {
            item = buildConversationItem(conversation);
        } else {
            updateConversationItem(item, conversation);
        }

        conversationList.prepend(item);

        if (!existed && conversation.id === selectedConversationId) {
            item.classList.add("is-active");
        }
    };

    const sendMarkRead = () => {
        if (!socket || socket.readyState !== WebSocket.OPEN || !selectedConversationId) {
            return;
        }
        socket.send(
            JSON.stringify({
                action: "mark_read",
                conversation_id: selectedConversationId,
            })
        );
    };

    const scheduleReconnect = () => {
        if (reconnectTimerId) {
            return;
        }
        setConnectionState("reconnecting");
        const delay = Math.min(1000 * 2 ** reconnectAttempts, 10000);
        reconnectAttempts += 1;
        reconnectTimerId = window.setTimeout(() => {
            reconnectTimerId = null;
            connectSocket();
        }, delay);
    };

    const connectSocket = () => {
        setConnectionState("connecting");
        socket = new WebSocket(`${websocketProtocol}://${window.location.host}${websocketPath}`);

        socket.addEventListener("open", () => {
            reconnectAttempts = 0;
            clearError();
            setConnectionState("live");
            sendMarkRead();
        });

        socket.addEventListener("message", (event) => {
            const payload = JSON.parse(event.data);
            if (payload.type === "error") {
                showError(payload.message);
                return;
            }

            if (payload.type === "conversation.read") {
                applySummaryDelta(payload.summary);
                const item = conversationList?.querySelector(`[data-conversation-id="${payload.conversation.id}"]`);
                if (item) {
                    updateConversationItem(item, payload.conversation);
                }
                return;
            }

            if (payload.type !== "message.created") {
                return;
            }

            clearError();
            applySummaryDelta(payload.summary);
            upsertConversation(payload.conversation);

            if (payload.conversation.id === selectedConversationId) {
                if (currentThreadPage === 1) {
                    appendMessageBubble(payload.message);
                    if (payload.message.sender_id !== currentUserId) {
                        sendMarkRead();
                        const activeItem = conversationList?.querySelector(
                            `[data-conversation-id="${selectedConversationId}"]`
                        );
                        ensureUnreadDot(activeItem, false);
                    }
                } else if (deliveryState) {
                    deliveryState.textContent = "Newer messages are available on the latest page.";
                }
            }
        });

        socket.addEventListener("close", (event) => {
            if (isShuttingDown) {
                return;
            }
            if (stopReconnectCodes.has(event.code)) {
                setConnectionState("offline");
                showError("Your session expired. Refresh the page and sign in again.");
                return;
            }
            scheduleReconnect();
        });
    };

    connectSocket();
    renderTotalConversationCount();
    renderUnreadCount();
    updateComposeState();

    window.addEventListener("beforeunload", () => {
        isShuttingDown = true;
        if (reconnectTimerId) {
            window.clearTimeout(reconnectTimerId);
            reconnectTimerId = null;
        }
        if (socket) {
            socket.close();
        }
    });

    if (replyInput) {
        replyInput.addEventListener("input", updateComposeState);
    }

    if (replyForm && replyInput) {
        replyForm.addEventListener("submit", (event) => {
            const body = replyInput.value.trim();
            if (!body) {
                event.preventDefault();
                showError("Enter a message before sending.");
                updateComposeState();
                return;
            }

            if (!socket || socket.readyState !== WebSocket.OPEN || !selectedConversationId || currentThreadPage !== 1) {
                return;
            }

            event.preventDefault();
            clearError();
            socket.send(
                JSON.stringify({
                    action: "send_message",
                    conversation_id: selectedConversationId,
                    body,
                })
            );
            replyInput.value = "";
            updateComposeState();
        });
    }
})();
