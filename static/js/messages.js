import { createMessagesUi } from "./messages_dom.js";
import { createMessagesSocket } from "./messages_socket.js";

const root = document.querySelector("[data-messages-root]");

if (root) {
    const ui = createMessagesUi(root);

    if (ui?.websocketPath) {
        const websocketProtocol = window.location.protocol === "https:" ? "wss" : "ws";
        const socket = createMessagesSocket({
            websocketUrl: `${websocketProtocol}://${window.location.host}${ui.websocketPath}`,
            onStateChange: ui.setConnectionState,
            onOpen() {
                ui.clearError();
                if (ui.selectedConversationId) {
                    socket.sendJson({
                        action: "mark_read",
                        conversation_id: ui.selectedConversationId,
                    });
                }
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
                ui.showError(message);
            },
            onAuthExpired() {
                ui.showError("Your session expired. Refresh the page and sign in again.");
            },
        });

        ui.init();

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
                socket.sendJson({
                    action: "send_message",
                    conversation_id: ui.selectedConversationId,
                    body,
                });
                ui.clearReplyInput();
            });
        }

        window.addEventListener("beforeunload", () => {
            socket.close();
        });
    }
}
