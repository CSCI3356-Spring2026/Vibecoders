export function createConversationListController({ conversationList, conversationUrl, selectedConversationId }) {
    const formatShortDate = (isoString) =>
        new Date(isoString).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
        });

    const initialFromName = (name) => {
        const trimmed = (name || "").trim();
        return trimmed ? trimmed.charAt(0).toUpperCase() : "?";
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

    const updateConversationItem = (item, conversation) => {
        item.querySelector("[data-role='conversation-name']").textContent = conversation.counterparty_name;
        item.querySelector("[data-role='conversation-date']").textContent = formatShortDate(conversation.last_message_at);
        item.querySelector("[data-role='conversation-subject']").textContent = conversation.listing_title;
        item.querySelector("[data-role='conversation-preview']").textContent =
            conversation.last_message_preview || "No messages yet.";
        appendConversationMedia(item.querySelector("[data-role='conversation-media']"), conversation);
        ensureUnreadDot(item, Boolean(conversation.has_unread));
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

    return {
        update(item, conversation) {
            updateConversationItem(item, conversation);
        },
        markUnread(item, hasUnread) {
            ensureUnreadDot(item, hasUnread);
        },
        upsert(conversation) {
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
        },
    };
}
