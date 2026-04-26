import { createAddressPicker } from "./listings-address-picker.js";

const STORAGE_PREFIX = "listing-wizard-draft:";
const STORAGE_VERSION = 1;
const DRAFT_MAX_AGE_MS = 72 * 60 * 60 * 1000;
const SAVE_DEBOUNCE_MS = 300;
const AUTOSAVE_EXCLUDED_FIELDS = new Set(["csrfmiddlewaretoken", "images"]);

const root = globalThis.document?.querySelector?.("[data-listing-form-wizard]");

if (root instanceof HTMLFormElement) {
    createListingWizard(root);
}

export function createListingWizard(form) {
    const addressPicker = createAddressPicker(form);

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

    const draftController = createDraftController();
    const restoredStepIndex = draftController.restore();
    if (Number.isInteger(restoredStepIndex)) {
        currentStepIndex = restoredStepIndex;
    }

    if (!isStepUnlocked(currentStepIndex)) {
        currentStepIndex = getLastUnlockedStepIndex();
    }

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
            draftController.scheduleSave();
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
        draftController.scheduleSave();
    });

    nextButton?.addEventListener("click", () => {
        const currentStep = panels[currentStepIndex];
        if (!canAdvanceFromStep(currentStep)) {
            return;
        }

        if (currentStepIndex < panels.length - 1) {
            currentStepIndex += 1;
            render();
            draftController.scheduleSave();
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
        draftController.scheduleSave();
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
        if (fieldName === "address" && addressPicker) {
            return addressPicker.isSelectionComplete();
        }

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
        setNodeText(reviewNodes.layout, `${rooms} bd - ${bathrooms} ba${squareFeet ? ` - ${squareFeet} sqft` : ""}`);
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

    function createDraftController() {
        const card = form.querySelector("[data-listing-draft-card]");
        const messageNode = form.querySelector("[data-listing-draft-message]");
        const detailNode = form.querySelector("[data-listing-draft-detail]");
        const clearButton = form.querySelector("[data-listing-draft-clear]");
        const storage = getLocalStorage();
        const storageKeySuffix = form.dataset.draftStorageKey || window.location.pathname;
        const storageKey = `${STORAGE_PREFIX}${storageKeySuffix}`;
        const formHasErrors = form.dataset.formHasErrors === "true";
        const timestampFormatter = new Intl.DateTimeFormat(undefined, {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
        let hasSavedDraft = false;
        let lastSavedAt = 0;
        let restoredFromDraft = false;
        let addressRequiresReselection = false;
        let saveTimeoutId = 0;

        clearButton?.addEventListener("click", () => {
            if (!storage) {
                return;
            }

            storage.removeItem(storageKey);
            hasSavedDraft = false;
            restoredFromDraft = false;
            addressRequiresReselection = false;
            lastSavedAt = 0;
            renderDraftStatus();
        });

        window.addEventListener?.("online", renderDraftStatus);
        window.addEventListener?.("offline", renderDraftStatus);
        window.addEventListener?.("pagehide", () => {
            saveDraft();
        });

        return {
            restore,
            scheduleSave,
        };

        function restore() {
            if (!storage) {
                renderDraftStatus();
                return null;
            }

            const draft = readDraft();
            if (!draft) {
                renderDraftStatus();
                return null;
            }

            hasSavedDraft = true;
            lastSavedAt = draft.savedAt;

            if (formHasErrors) {
                renderDraftStatus();
                return null;
            }

            const restoreResult = applyDraft(draft);
            restoredFromDraft = true;
            addressRequiresReselection = restoreResult.addressRequiresReselection;
            renderDraftStatus();

            if (!Number.isInteger(draft.stepIndex)) {
                return null;
            }

            return Math.max(0, Math.min(draft.stepIndex, panels.length - 1));
        }

        function scheduleSave() {
            if (!storage) {
                return;
            }

            window.clearTimeout(saveTimeoutId);
            saveTimeoutId = window.setTimeout(() => {
                saveDraft();
            }, SAVE_DEBOUNCE_MS);
        }

        function saveDraft() {
            if (!storage) {
                return;
            }

            const draft = {
                version: STORAGE_VERSION,
                savedAt: Date.now(),
                stepIndex: currentStepIndex,
                fields: collectDraftFields(),
            };

            try {
                storage.setItem(storageKey, JSON.stringify(draft));
                hasSavedDraft = true;
                lastSavedAt = draft.savedAt;
                restoredFromDraft = false;
                addressRequiresReselection = false;
                renderDraftStatus();
            } catch {
                // Ignore storage write failures so the form remains usable.
            }
        }

        function readDraft() {
            try {
                const rawDraft = storage.getItem(storageKey);
                if (!rawDraft) {
                    return null;
                }

                const parsedDraft = JSON.parse(rawDraft);
                if (
                    parsedDraft?.version !== STORAGE_VERSION ||
                    !parsedDraft.fields ||
                    !Number.isFinite(parsedDraft.savedAt)
                ) {
                    storage.removeItem(storageKey);
                    return null;
                }

                if (Date.now() - parsedDraft.savedAt > DRAFT_MAX_AGE_MS) {
                    storage.removeItem(storageKey);
                    return null;
                }

                return parsedDraft;
            } catch {
                return null;
            }
        }

        function applyDraft(draft) {
            const fields = draft.fields || {};
            const addressRestore = addressPicker.restoreSelection({
                addressValue: fields.address,
                tokenValue: fields.verified_address_token,
                savedAt: draft.savedAt,
            });

            Object.entries(fields).forEach(([fieldName, value]) => {
                if (fieldName === "address" || fieldName === "verified_address_token") {
                    return;
                }
                applyFieldValue(fieldName, value);
            });

            return {
                addressRequiresReselection: addressRestore.requiresReselection,
            };
        }

        function collectDraftFields() {
            const fieldNames = Array.from(form.elements).reduce((names, element) => {
                if (!isRestorableField(element)) {
                    return names;
                }
                names.add(element.name);
                return names;
            }, new Set());

            const payload = {};
            fieldNames.forEach((fieldName) => {
                const value = serializeFieldValue(fieldName);
                if (value !== undefined) {
                    payload[fieldName] = value;
                }
            });
            return payload;
        }

        function serializeFieldValue(fieldName) {
            const fields = getFields(fieldName);
            if (!fields.length) {
                return undefined;
            }

            const firstField = fields[0];
            if (firstField instanceof HTMLInputElement && firstField.type === "checkbox") {
                if (fields.length === 1) {
                    return firstField.checked;
                }
                return fields.filter((field) => field.checked).map((field) => field.value);
            }

            if (firstField instanceof HTMLInputElement && firstField.type === "radio") {
                return fields.find((field) => field.checked)?.value || "";
            }

            if (firstField instanceof HTMLSelectElement && firstField.multiple) {
                return Array.from(firstField.selectedOptions).map((option) => option.value);
            }

            return firstField.value;
        }

        function applyFieldValue(fieldName, value) {
            const fields = getFields(fieldName);
            if (!fields.length) {
                return;
            }

            const firstField = fields[0];
            if (firstField instanceof HTMLInputElement && firstField.type === "checkbox") {
                if (fields.length === 1) {
                    firstField.checked = Boolean(value);
                    return;
                }

                const selectedValues = new Set(Array.isArray(value) ? value.map(String) : []);
                fields.forEach((field) => {
                    field.checked = selectedValues.has(String(field.value));
                });
                return;
            }

            if (firstField instanceof HTMLInputElement && firstField.type === "radio") {
                fields.forEach((field) => {
                    field.checked = String(value || "") === String(field.value);
                });
                return;
            }

            if (firstField instanceof HTMLSelectElement && firstField.multiple) {
                const selectedValues = new Set(Array.isArray(value) ? value.map(String) : []);
                Array.from(firstField.options).forEach((option) => {
                    option.selected = selectedValues.has(String(option.value));
                });
                return;
            }

            firstField.value = value == null ? "" : String(value);
        }

        function renderDraftStatus() {
            if (!(card instanceof HTMLElement)) {
                return;
            }

            if (!hasSavedDraft && navigator.onLine !== false) {
                card.hidden = true;
                return;
            }

            card.hidden = false;

            if (navigator.onLine === false) {
                setNodeText(messageNode, "You're offline. Keep working and we'll keep this listing draft on this device.");
            } else if (restoredFromDraft) {
                setNodeText(messageNode, "Recovered your saved listing draft from this browser.");
            } else if (hasSavedDraft) {
                setNodeText(messageNode, "Listing draft saved on this device.");
            } else {
                setNodeText(messageNode, "Offline changes will be kept on this device.");
            }

            const detailParts = [];
            if (lastSavedAt) {
                detailParts.push(`Last saved ${timestampFormatter.format(new Date(lastSavedAt))}`);
            }
            if (addressRequiresReselection) {
                detailParts.push("Re-select the verified address before submitting.");
            }

            setNodeText(detailNode, detailParts.join(" | "));
            if (clearButton) {
                clearButton.hidden = !hasSavedDraft;
            }
        }

        function isRestorableField(element) {
            if (!(element instanceof HTMLElement) || typeof element.name !== "string" || !element.name) {
                return false;
            }

            if (AUTOSAVE_EXCLUDED_FIELDS.has(element.name)) {
                return false;
            }

            return !(element instanceof HTMLInputElement && element.type === "file");
        }
    }
}

function getLocalStorage() {
    try {
        const storage = window.localStorage;
        const probeKey = "__listing_wizard_probe__";
        storage.setItem(probeKey, probeKey);
        storage.removeItem(probeKey);
        return storage;
    } catch {
        return null;
    }
}
