document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-legal-review-form]");
    if (!(form instanceof HTMLFormElement)) {
        return;
    }

    const cards = Array.from(form.querySelectorAll("[data-legal-review-card]"));
    const submitButton = form.querySelector("[data-legal-review-submit]");

    const updateSubmitState = () => {
        const allReviewed = cards.every((card) => {
            const checkbox = card.querySelector("[data-legal-review-checkbox]");
            const hiddenInput = card.querySelector("[data-legal-review-hidden]");
            return (
                checkbox instanceof HTMLInputElement
                && hiddenInput instanceof HTMLInputElement
                && hiddenInput.value === "true"
                && checkbox.checked
                && !checkbox.disabled
            );
        });

        if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = !allReviewed;
        }
    };

    const markReviewed = (card) => {
        const hiddenInput = card.querySelector("[data-legal-review-hidden]");
        const checkbox = card.querySelector("[data-legal-review-checkbox]");
        const status = card.querySelector("[data-legal-review-status]");
        if (!(hiddenInput instanceof HTMLInputElement) || !(checkbox instanceof HTMLInputElement)) {
            return;
        }

        hiddenInput.value = "true";
        checkbox.disabled = false;
        if (status instanceof HTMLElement) {
            status.textContent = card.dataset.reviewCompleteLabel || "Reviewed.";
        }
        updateSubmitState();
    };

    cards.forEach((card) => {
        const pane = card.querySelector("[data-legal-review-pane]");
        const checkbox = card.querySelector("[data-legal-review-checkbox]");
        if (!(pane instanceof HTMLElement) || !(checkbox instanceof HTMLInputElement)) {
            return;
        }

        const handleScroll = () => {
            const remaining = pane.scrollHeight - pane.scrollTop - pane.clientHeight;
            if (remaining <= 8) {
                markReviewed(card);
            }
        };

        pane.addEventListener("scroll", handleScroll, { passive: true });
        checkbox.addEventListener("change", updateSubmitState);
        handleScroll();
    });

    updateSubmitState();
});
