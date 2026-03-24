const root = document.querySelector("[data-listing-form-wizard]");

if (root instanceof HTMLFormElement) {
    createListingWizard(root);
}

function createListingWizard(form) {
    const panels = Array.from(form.querySelectorAll("[data-step-panel]"))
        .map((panel) => ({
            index: Number(panel.dataset.stepPanel || 0),
            panel,
            navButton: form.querySelector(`[data-step-nav="${panel.dataset.stepPanel}"]`),
            title: panel.dataset.stepTitle || `Step ${panel.dataset.stepPanel}`,
            subtitle: panel.dataset.stepSubtitle || "",
            requiredFields: (panel.dataset.stepCompleteFields || "")
                .split(",")
                .map((fieldName) => fieldName.trim())
                .filter(Boolean),
        }))
        .sort((left, right) => left.index - right.index);

    if (!panels.length) {
        return;
    }

    const progressCopy = form.querySelector("[data-wizard-progress-copy]");
    const progressBar = form.querySelector("[data-wizard-progress-bar]");
    const footerTitle = form.querySelector("[data-wizard-footer-title]");
    const footerSubtitle = form.querySelector("[data-wizard-footer-subtitle]");
    const previousButton = form.querySelector("[data-step-prev]");
    const nextButton = form.querySelector("[data-step-next]");
    const submitButton = form.querySelector("[data-step-submit]");
    const imageInput = getFirstField("images");
    const reviewNodes = {
        status: form.querySelector("[data-review-status]"),
        title: form.querySelector("[data-review-title]"),
        address: form.querySelector("[data-review-address]"),
        rent: form.querySelector("[data-review-rent]"),
        monthly: form.querySelector("[data-review-monthly]"),
        layout: form.querySelector("[data-review-layout]"),
        dates: form.querySelector("[data-review-dates]"),
        photos: form.querySelector("[data-review-photos]"),
        visibility: form.querySelector("[data-review-visibility]"),
    };
    const moneyFormatter = new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
    });
    const dateFormatter = new Intl.DateTimeFormat(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
    });

    let currentStepIndex = resolveInitialStepIndex();
    form.classList.add("is-enhanced");

    panels.forEach((step) => {
        if (!step.navButton) {
            return;
        }

        step.navButton.addEventListener("click", () => {
            if (!isStepUnlocked(step.index)) {
                return;
            }
            currentStepIndex = step.index;
            render();
        });
    });

    form.addEventListener("input", handleFieldMutation);
    form.addEventListener("change", handleFieldMutation);
    form.addEventListener("submit", handleSubmit);

    previousButton?.addEventListener("click", () => {
        if (currentStepIndex === 0) {
            return;
        }
        currentStepIndex -= 1;
        render();
    });

    nextButton?.addEventListener("click", () => {
        const currentStep = panels[currentStepIndex];
        if (!canAdvanceFromStep(currentStep)) {
            return;
        }

        if (currentStepIndex < panels.length - 1) {
            currentStepIndex += 1;
            render();
        }
    });

    render();

    function handleFieldMutation(event) {
        const field = event.target;
        if (!field || typeof field.name !== "string" || !field.name) {
            return;
        }

        clearFieldValidity(field.name);

        if (!isStepUnlocked(currentStepIndex)) {
            currentStepIndex = getLastUnlockedStepIndex();
        }

        render();
    }

    function handleSubmit(event) {
        const firstIncompleteRequiredStep = panels.find(
            (step) => step.requiredFields.length > 0 && !isStepComplete(step)
        );

        if (!firstIncompleteRequiredStep) {
            return;
        }

        event.preventDefault();
        currentStepIndex = firstIncompleteRequiredStep.index;
        render();
        revealIncompleteField(firstIncompleteRequiredStep);
    }

    function render() {
        const lastUnlockedStepIndex = getLastUnlockedStepIndex();

        panels.forEach((step) => {
            const isActive = step.index === currentStepIndex;
            const isComplete = isStepComplete(step);
            const unlocked = isStepUnlocked(step.index);

            step.panel.classList.toggle("is-active", isActive);
            step.panel.hidden = !isActive;

            if (!step.navButton) {
                return;
            }

            step.navButton.classList.toggle("is-active", isActive);
            step.navButton.classList.toggle("is-complete", isComplete);
            step.navButton.classList.toggle("is-locked", !unlocked);
            step.navButton.disabled = !unlocked;
            step.navButton.setAttribute("aria-current", isActive ? "step" : "false");
            step.navButton.setAttribute("aria-disabled", unlocked ? "false" : "true");

            const stateNode = step.navButton.querySelector("[data-step-state]");
            if (stateNode) {
                stateNode.textContent = getStepStateLabel({
                    isActive,
                    isComplete,
                    unlocked,
                    isLastUnlocked: step.index === lastUnlockedStepIndex,
                });
            }
        });

        if (progressCopy) {
            progressCopy.textContent = `Step ${currentStepIndex + 1} of ${panels.length}`;
        }

        if (progressBar) {
            progressBar.style.width = `${((currentStepIndex + 1) / panels.length) * 100}%`;
        }

        if (footerTitle) {
            footerTitle.textContent = panels[currentStepIndex].title;
        }

        if (footerSubtitle) {
            footerSubtitle.textContent = panels[currentStepIndex].subtitle;
        }

        if (previousButton) {
            previousButton.hidden = currentStepIndex === 0;
        }

        if (nextButton) {
            nextButton.hidden = currentStepIndex === panels.length - 1;
        }

        if (submitButton) {
            submitButton.hidden = currentStepIndex !== panels.length - 1;
        }

        renderReview();
    }

    function resolveInitialStepIndex() {
        const firstErrorStep = panels.find((step) => step.panel.querySelector(".app-field-error"));
        if (firstErrorStep) {
            return firstErrorStep.index;
        }

        const firstIncompleteRequiredStep = panels.find(
            (step) => step.requiredFields.length > 0 && !isStepComplete(step)
        );
        if (firstIncompleteRequiredStep) {
            return firstIncompleteRequiredStep.index;
        }

        return panels[panels.length - 1].index;
    }

    function getStepStateLabel({ isActive, isComplete, unlocked, isLastUnlocked }) {
        if (isActive) {
            return "Current";
        }
        if (!unlocked) {
            return "Locked";
        }
        if (isComplete) {
            return "Complete";
        }
        if (isLastUnlocked) {
            return "Ready";
        }
        return "Open";
    }

    function canAdvanceFromStep(step) {
        if (!step || isStepComplete(step) || step.requiredFields.length === 0) {
            return true;
        }

        revealIncompleteField(step);
        return false;
    }

    function revealIncompleteField(step) {
        const missingFieldName = step.requiredFields.find((fieldName) => !isFieldFilled(fieldName));
        if (!missingFieldName) {
            return;
        }

        const fields = getFields(missingFieldName);
        fields.forEach((field) => {
            if (typeof field.setCustomValidity === "function") {
                field.setCustomValidity("Complete this field to continue.");
            }
        });

        const focusTarget = fields.find((field) => typeof field.reportValidity === "function") || fields[0];
        if (focusTarget && typeof focusTarget.reportValidity === "function") {
            focusTarget.reportValidity();
        }
        focusTarget?.focus?.();
    }

    function isStepComplete(step) {
        if (!step.requiredFields.length) {
            return false;
        }
        return step.requiredFields.every((fieldName) => isFieldFilled(fieldName));
    }

    function isStepUnlocked(stepIndex) {
        return panels
            .filter((step) => step.index < stepIndex && step.requiredFields.length > 0)
            .every((step) => isStepComplete(step));
    }

    function getLastUnlockedStepIndex() {
        let lastUnlockedIndex = 0;

        panels.forEach((step) => {
            if (isStepUnlocked(step.index)) {
                lastUnlockedIndex = step.index;
            }
        });

        return lastUnlockedIndex;
    }

    function getFields(fieldName) {
        return Array.from(form.elements).filter(
            (element) => element instanceof HTMLElement && "name" in element && element.name === fieldName
        );
    }

    function getFirstField(fieldName) {
        return getFields(fieldName)[0] || null;
    }

    function clearFieldValidity(fieldName) {
        getFields(fieldName).forEach((field) => {
            if (typeof field.setCustomValidity === "function") {
                field.setCustomValidity("");
            }
        });
    }

    function isFieldFilled(fieldName) {
        const fields = getFields(fieldName);
        if (!fields.length) {
            return true;
        }

        const firstField = fields[0];

        if (firstField instanceof HTMLInputElement && firstField.type === "checkbox" && fields.length === 1) {
            return firstField.checked;
        }

        if (firstField instanceof HTMLInputElement && firstField.type === "radio") {
            return fields.some((field) => field.checked);
        }

        if (firstField instanceof HTMLInputElement && firstField.type === "file") {
            return Boolean(firstField.files?.length);
        }

        if (firstField instanceof HTMLSelectElement && firstField.multiple) {
            return Array.from(firstField.selectedOptions).length > 0;
        }

        return String(firstField.value || "").trim() !== "";
    }

    function getFieldValue(fieldName) {
        const field = getFirstField(fieldName);
        if (!field) {
            return "";
        }

        if (field instanceof HTMLInputElement && field.type === "checkbox") {
            return field.checked ? "true" : "";
        }

        return String(field.value || "").trim();
    }

    function getChoiceLabel(fieldName) {
        const field = getFirstField(fieldName);
        if (!(field instanceof HTMLSelectElement)) {
            return "";
        }

        const selectedOption = field.selectedOptions[0];
        return selectedOption ? selectedOption.textContent.trim() : "";
    }

    function parseAmount(rawValue) {
        if (!rawValue) {
            return null;
        }

        const value = Number.parseFloat(rawValue);
        return Number.isFinite(value) ? value : null;
    }

    function formatMoney(value) {
        return `${moneyFormatter.format(value)}/mo`;
    }

    function formatDate(value) {
        if (!value) {
            return "";
        }

        const parsed = new Date(`${value}T00:00:00`);
        if (Number.isNaN(parsed.getTime())) {
            return value;
        }

        return dateFormatter.format(parsed);
    }

    function getExistingPhotoCount() {
        const removeImageInputs = Array.from(form.querySelectorAll('input[name="remove_images"]'));
        if (!removeImageInputs.length) {
            return 0;
        }

        return removeImageInputs.filter((input) => !input.checked).length;
    }

    function getUploadedPhotoCount() {
        if (!(imageInput instanceof HTMLInputElement)) {
            return 0;
        }

        return imageInput.files?.length || 0;
    }

    function renderReview() {
        const title = getFieldValue("title") || "New listing";
        const address = getFieldValue("address") || "Add address";
        const price = parseAmount(getFieldValue("price"));
        const utilities = parseAmount(getFieldValue("utilities_estimate")) || 0;
        const parking = parseAmount(getFieldValue("parking_fee")) || 0;
        const rooms = getFieldValue("rooms") || "--";
        const bathrooms = getFieldValue("bathrooms") || "--";
        const squareFeet = getFieldValue("sq_ft");
        const startDate = formatDate(getFieldValue("start_date")) || "Start";
        const endDate = formatDate(getFieldValue("end_date")) || "End";
        const isHidden = Boolean(getFieldValue("is_hidden"));
        const statusLabel = getChoiceLabel("status") || "Available";
        const monthlyTotal = price === null ? null : price + utilities + parking;
        const photoCount = getExistingPhotoCount() + getUploadedPhotoCount();

        setNodeText(reviewNodes.title, title);
        setNodeText(reviewNodes.address, address);
        setNodeText(reviewNodes.rent, price === null ? "--" : formatMoney(price));
        setNodeText(reviewNodes.monthly, monthlyTotal === null ? "--" : formatMoney(monthlyTotal));
        setNodeText(
            reviewNodes.layout,
            `${rooms} bd • ${bathrooms} ba${squareFeet ? ` • ${squareFeet} sqft` : ""}`
        );
        setNodeText(reviewNodes.dates, `${startDate} to ${endDate}`);
        setNodeText(reviewNodes.photos, `${photoCount} ${photoCount === 1 ? "photo" : "photos"}`);
        setNodeText(reviewNodes.status, isHidden ? "Hidden draft" : statusLabel);
        setNodeText(reviewNodes.visibility, isHidden ? "Hidden draft" : statusLabel);
    }

    function setNodeText(node, value) {
        if (node) {
            node.textContent = value;
        }
    }
}
