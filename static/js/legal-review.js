document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("[data-legal-review-form]");
    if (!(form instanceof HTMLFormElement)) {
        return;
    }

    const cards = Array.from(form.querySelectorAll("[data-legal-review-card]"));
    const submitButton = form.querySelector("[data-legal-review-submit]");
    const stepTriggers = Array.from(form.querySelectorAll("[data-legal-review-step-trigger]"));
    const nextButton = form.querySelector("[data-legal-review-next]");
    const prevButton = form.querySelector("[data-legal-review-prev]");
    let activeStep = "privacy";

    const getCard = (key) => cards.find((card) => card.dataset.reviewKey === key);
    const isAccepted = (key) => {
        const card = getCard(key);
        if (!(card instanceof HTMLElement)) {
            return false;
        }
        const checkbox = card.querySelector("[data-legal-review-checkbox]");
        const hiddenInput = card.querySelector("[data-legal-review-hidden]");
        return (
            checkbox instanceof HTMLInputElement
            && hiddenInput instanceof HTMLInputElement
            && hiddenInput.value === "true"
            && checkbox.checked
            && !checkbox.disabled
        );
    };

    const hasErrors = (key) => {
        const card = getCard(key);
        return card instanceof HTMLElement && Boolean(card.querySelector(".errorlist, .app-field-error"));
    };

    const renderStep = (stepKey) => {
        activeStep = stepKey;
        cards.forEach((card) => {
            const isActive = card.dataset.reviewKey === stepKey;
            card.hidden = !isActive;
            card.classList.toggle("is-active", isActive);
        });

        stepTriggers.forEach((trigger) => {
            if (!(trigger instanceof HTMLButtonElement)) {
                return;
            }
            const isActive = trigger.dataset.stepTarget === stepKey;
            trigger.classList.toggle("is-active", isActive);
        });
    };

    const updateSubmitState = () => {
        const privacyAccepted = isAccepted("privacy");
        const termsAccepted = isAccepted("terms");

        if (submitButton instanceof HTMLButtonElement) {
            submitButton.disabled = !(privacyAccepted && termsAccepted);
            submitButton.hidden = activeStep !== "terms";
        }

        if (nextButton instanceof HTMLButtonElement) {
            nextButton.disabled = !privacyAccepted;
        }

        stepTriggers.forEach((trigger) => {
            if (!(trigger instanceof HTMLButtonElement)) {
                return;
            }
            if (trigger.dataset.stepTarget === "terms") {
                trigger.disabled = !privacyAccepted;
            }
        });

        if (!privacyAccepted && activeStep === "terms") {
            renderStep("privacy");
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

    stepTriggers.forEach((trigger) => {
        if (!(trigger instanceof HTMLButtonElement)) {
            return;
        }
        trigger.addEventListener("click", () => {
            if (trigger.disabled) {
                return;
            }
            renderStep(trigger.dataset.stepTarget || "privacy");
            updateSubmitState();
        });
    });

    if (nextButton instanceof HTMLButtonElement) {
        nextButton.addEventListener("click", () => {
            if (!nextButton.disabled) {
                renderStep("terms");
                updateSubmitState();
            }
        });
    }

    if (prevButton instanceof HTMLButtonElement) {
        prevButton.addEventListener("click", () => {
            renderStep("privacy");
            updateSubmitState();
        });
    }

    if (hasErrors("privacy")) {
        renderStep("privacy");
    } else if (hasErrors("terms")) {
        renderStep("terms");
    } else if (isAccepted("privacy") && !isAccepted("terms")) {
        renderStep("terms");
    }

    updateSubmitState();
});
