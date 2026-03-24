const confirmRoots = document.querySelectorAll("[data-inline-confirm]");

function closeConfirm(root) {
    const panel = root.querySelector("[data-inline-confirm-panel]");
    const trigger = root.querySelector("[data-inline-confirm-open]");
    if (panel) {
        panel.hidden = true;
    }
    if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
    }
    root.classList.remove("is-open");
}

function openConfirm(root) {
    confirmRoots.forEach((otherRoot) => {
        if (otherRoot !== root) {
            closeConfirm(otherRoot);
        }
    });

    const panel = root.querySelector("[data-inline-confirm-panel]");
    const trigger = root.querySelector("[data-inline-confirm-open]");
    if (panel) {
        panel.hidden = false;
    }
    if (trigger) {
        trigger.setAttribute("aria-expanded", "true");
    }
    root.classList.add("is-open");
}

confirmRoots.forEach((root) => {
    const trigger = root.querySelector("[data-inline-confirm-open]");
    const closeButton = root.querySelector("[data-inline-confirm-close]");
    const panel = root.querySelector("[data-inline-confirm-panel]");

    if (!trigger || !panel) {
        return;
    }

    panel.hidden = true;
    trigger.setAttribute("aria-expanded", "false");

    trigger.addEventListener("click", () => {
        if (root.classList.contains("is-open")) {
            closeConfirm(root);
            return;
        }
        openConfirm(root);
    });

    closeButton?.addEventListener("click", () => {
        closeConfirm(root);
    });
});

document.addEventListener("click", (event) => {
    confirmRoots.forEach((root) => {
        if (!root.contains(event.target)) {
            closeConfirm(root);
        }
    });
});

document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
        return;
    }
    confirmRoots.forEach((root) => closeConfirm(root));
});
