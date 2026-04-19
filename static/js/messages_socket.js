const STOP_RECONNECT_CODES = new Set([4401, 4403, 1008]);

export function createMessagesSocket({
    websocketUrl,
    onStateChange,
    onOpen,
    onPayload,
    onErrorMessage,
    onAuthExpired,
    onConnectionLost,
}) {
    let socket = null;
    let reconnectAttempts = 0;
    let reconnectTimerId = null;
    let isShuttingDown = false;

    const setState = (state) => {
        onStateChange?.(state);
    };

    const clearReconnectTimer = () => {
        if (reconnectTimerId) {
            window.clearTimeout(reconnectTimerId);
            reconnectTimerId = null;
        }
    };

    const isOpen = () => Boolean(socket && socket.readyState === WebSocket.OPEN);

    const connect = () => {
        setState("connecting");
        socket = new WebSocket(websocketUrl);

        socket.addEventListener("open", () => {
            reconnectAttempts = 0;
            setState("live");
            onOpen?.();
        });

        socket.addEventListener("message", (event) => {
            let payload;
            try {
                payload = JSON.parse(event.data);
            } catch {
                onErrorMessage?.("Unexpected realtime payload received.");
                return;
            }

            if (payload.type === "error") {
                onErrorMessage?.(payload.message);
                return;
            }

            onPayload?.(payload);
        });

        socket.addEventListener("close", (event) => {
            if (isShuttingDown) {
                return;
            }

            if (STOP_RECONNECT_CODES.has(event.code)) {
                setState("offline");
                onAuthExpired?.();
                return;
            }

            onConnectionLost?.();
            if (reconnectTimerId) {
                return;
            }

            setState("reconnecting");
            const delay = Math.min(1000 * 2 ** reconnectAttempts, 10000);
            reconnectAttempts += 1;
            reconnectTimerId = window.setTimeout(() => {
                reconnectTimerId = null;
                connect();
            }, delay);
        });
    };

    connect();

    return {
        isOpen,
        sendJson(payload) {
            if (!isOpen()) {
                return false;
            }
            socket.send(JSON.stringify(payload));
            return true;
        },
        close() {
            isShuttingDown = true;
            clearReconnectTimer();
            if (socket) {
                socket.close();
            }
        },
    };
}
