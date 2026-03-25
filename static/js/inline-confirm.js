const confirmRoots = document.querySelectorAll("[data-inline-confirm]");
const PANEL_OFFSET = 8;
const VIEWPORT_MARGIN = 12;

function closeConfirm(root) {
    const panel = root.querySelector("[data-inline-confirm-panel]");
    const trigger = root.querySelector("[data-inline-confirm-open]");
    if (panel) {
        panel.hidden = true;
        panel.style.top = "";
        panel.style.left = "";
        panel.style.visibility = "";
    }
    if (trigger) {
        trigger.setAttribute("aria-expanded", "false");
    }
    root.classList.remove("is-open");
}

function clamp(value, minimum, maximum) {
    return Math.min(Math.max(value, minimum), maximum);
}

function positionConfirm(root) {
    const panel = root.querySelector("[data-inline-confirm-panel]");
    const trigger = root.querySelector("[data-inline-confirm-open]");
    if (!panel || !trigger || panel.hidden) {
        return;
    }

    const triggerRect = trigger.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const maxLeft = Math.max(VIEWPORT_MARGIN, window.innerWidth - panelRect.width - VIEWPORT_MARGIN);
    const preferredLeft = triggerRect.right - panelRect.width;
    const left = clamp(preferredLeft, VIEWPORT_MARGIN, maxLeft);

    const belowTop = triggerRect.bottom + PANEL_OFFSET;
    const aboveTop = triggerRect.top - panelRect.height - PANEL_OFFSET;
    const canOpenBelow = belowTop + panelRect.height <= window.innerHeight - VIEWPORT_MARGIN;
    const canOpenAbove = aboveTop >= VIEWPORT_MARGIN;

    let top = belowTop;
    if (!canOpenBelow && canOpenAbove) {
        top = aboveTop;
    } else if (!canOpenBelow) {
        top = Math.max(VIEWPORT_MARGIN, window.innerHeight - panelRect.height - VIEWPORT_MARGIN);
    }

    panel.style.left = `${Math.round(left)}px`;
    panel.style.top = `${Math.round(top)}px`;
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
        panel.style.visibility = "hidden";
        panel.hidden = false;
    }
    if (trigger) {
        trigger.setAttribute("aria-expanded", "true");
    }
    root.classList.add("is-open");
    positionConfirm(root);
    if (panel) {
        panel.style.visibility = "";
    }
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

function repositionOpenConfirms() {
    confirmRoots.forEach((root) => {
        if (root.classList.contains("is-open")) {
            positionConfirm(root);
        }
    });
}

window.addEventListener("resize", repositionOpenConfirms);
document.addEventListener("scroll", repositionOpenConfirms, true);
