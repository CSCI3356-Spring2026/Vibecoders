document.addEventListener("DOMContentLoaded", () => {
    const notifications = Array.from(document.querySelectorAll("[data-app-notification]"));
    if (notifications.length === 0) {
        return;
    }

    const closeNotification = (notification) => {
        if (!(notification instanceof HTMLElement) || notification.dataset.closing === "true") {
            return;
        }

        notification.dataset.closing = "true";
        notification.classList.add("is-closing");
        window.setTimeout(() => {
            notification.remove();
        }, 180);
    };

    notifications.forEach((notification) => {
        const dismissButton = notification.querySelector("[data-app-notification-dismiss]");
        if (dismissButton instanceof HTMLButtonElement) {
            dismissButton.addEventListener("click", () => closeNotification(notification));
        }

        const autoDismiss = Number.parseInt(notification.dataset.autoDismiss || "", 10);
        if (!Number.isNaN(autoDismiss) && autoDismiss > 0) {
            window.setTimeout(() => closeNotification(notification), autoDismiss);
        }
    });
});
