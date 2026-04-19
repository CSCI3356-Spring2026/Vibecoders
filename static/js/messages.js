import { createMessagesUi } from "./messages_dom.js";
import { createMessagesSocket } from "./messages_socket.js";

const root = document.querySelector("[data-messages-root]");

const getCookie = (name) => {
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const cookie of cookies) {
        const trimmed = cookie.trim();
        if (trimmed.startsWith(`${name}=`)) {
            return decodeURIComponent(trimmed.slice(name.length + 1));
        }
    }
    return "";
};

const createClientMessageId = () => {
    if (globalThis.crypto?.randomUUID) {
        return globalThis.crypto.randomUUID();
    }
    return `msg-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
};

if (root) {
    const ui = createMessagesUi(root);

    const markSelectedConversationRead = async () => {
        if (!ui.selectedConversationId || ui.currentThreadPage !== 1) {
            return;
        }
        const url = ui.readUrl(ui.selectedConversationId);
        if (!url) {
            return;
        }

        try {
            const response = await window.fetch(url, {
                method: "POST",
                headers: {
                    "X-CSRFToken": getCookie("csrftoken"),
                    "X-Requested-With": "XMLHttpRequest",
                },
            });
            if (response.ok) {
                ui.markSelectedConversationReadLocally();
            }
        } catch {
            // Leave the thread state unchanged; websocket read sync can still reconcile later.
        }
    };

    if (ui?.websocketPath) {
        const websocketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
        const socket = createMessagesSocket({
            websocketUrl: `${websocketProtocol}://${window.location.host}${ui.websocketPath}`,
            onStateChange(state) {
                ui.setConnectionState(state);
            },
            onOpen() {
                ui.clearError();
            },
            onPayload(payload) {
                if (payload.type === "conversation.read") {
                    ui.handleConversationRead(payload);
                    return;
                }

                if (payload.type !== "message.created") {
                    return;
                }

                ui.handleMessageCreated(payload, {
                    onSelectedInboundMessage() {
                        socket.sendJson({
                            action: "mark_read",
                            conversation_id: ui.selectedConversationId,
                        });
                    },
                });
            },
            onErrorMessage(message) {
                ui.failPendingSend();
                ui.showError(message);
            },
            onAuthExpired() {
                ui.failPendingSend();
                ui.showError("Your session expired. Refresh the page and sign in again.");
            },
            onConnectionLost() {
                ui.failPendingSend();
                ui.showError("Realtime connection dropped before delivery. Your draft is still here.");
            },
        });

        ui.init();
        void markSelectedConversationRead();

        if (ui.replyInput) {
            ui.replyInput.addEventListener("input", ui.updateComposeState);
        }

        if (ui.replyForm && ui.replyInput) {
            ui.replyForm.addEventListener("submit", (event) => {
                const body = ui.getReplyBody();
                if (!body) {
                    event.preventDefault();
                    ui.showError("Enter a message before sending.");
                    ui.updateComposeState();
                    return;
                }

                if (!socket.isOpen() || !ui.selectedConversationId || ui.currentThreadPage !== 1) {
                    return;
                }

                event.preventDefault();
                ui.clearError();
                const clientMessageId = createClientMessageId();
                ui.setPendingSend(clientMessageId);
                const sent = socket.sendJson({
                    action: "send_message",
                    conversation_id: ui.selectedConversationId,
                    body,
                    client_message_id: clientMessageId,
                });
                if (!sent) {
                    ui.failPendingSend();
                    ui.showError("Realtime send is unavailable. Try again or refresh the page.");
                }
            });
        }

        window.addEventListener("beforeunload", () => {
            socket.close();
        });
    }
}
