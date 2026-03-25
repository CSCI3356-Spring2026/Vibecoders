const DEFAULT_STATUS = "Search and choose a verified address suggestion before publishing.";
const SAVED_STATUS = "Keeping the saved verified address.";
const BLOCKED_STATUS =
    "Verified address search is unavailable right now. Listing authoring is blocked until Geoapify autocomplete is configured.";
const LOOKUP_STATUS = "Looking up verified addresses...";
const EMPTY_RESULTS_STATUS = "No verified matches yet. Refine the address.";
const CHOOSE_STATUS = "Choose a verified address suggestion.";
const VERIFIED_STATUS = "Verified address selected.";
const UNAVAILABLE_STATUS = "Address suggestions are unavailable right now.";
const SELECTION_REQUIRED_MESSAGE = "Select a verified address suggestion.";
const MIN_QUERY_LENGTH = 3;
const LOOKUP_DEBOUNCE_MS = 250;

const NOOP_ADDRESS_PICKER = {
    isSelectionComplete() {
        return true;
    },
};

export function createAddressPicker(form) {
    const pickerRoot = form.querySelector("[data-address-picker]");
    const addressInput = form.querySelector("[data-address-input]");
    const tokenInput = form.querySelector("[data-address-token-input]");
    const suggestionsNode = form.querySelector("[data-address-suggestions]");
    const statusNode = form.querySelector("[data-address-status]");

    if (
        !(pickerRoot instanceof HTMLElement) ||
        !(addressInput instanceof HTMLInputElement) ||
        !(tokenInput instanceof HTMLInputElement) ||
        !(suggestionsNode instanceof HTMLElement) ||
        !(statusNode instanceof HTMLElement)
    ) {
        return NOOP_ADDRESS_PICKER;
    }

    const enabled = pickerRoot.dataset.addressPickerEnabled === "true";
    const suggestionsUrl = pickerRoot.dataset.addressSuggestionsUrl || "";
    const initialAddress = (pickerRoot.dataset.initialAddress || "").trim();
    const savedSelectionLabel =
        pickerRoot.dataset.addressInitiallyVerified === "true"
            ? (pickerRoot.dataset.selectedLabel || initialAddress).trim()
            : "";
    let selectedLabel = (pickerRoot.dataset.selectedLabel || "").trim();
    let debounceId = 0;
    let activeController = null;
    let latestRequestId = 0;

    if (!selectedLabel && tokenInput.value.trim()) {
        selectedLabel = addressInput.value.trim();
    }

    addressInput.addEventListener("input", handleAddressInput);
    form.addEventListener("submit", handleSubmit);

    return {
        isSelectionComplete,
    };

    function isSelectionComplete() {
        const currentAddress = addressInput.value.trim();
        if (!currentAddress) {
            return false;
        }
        if (tokenInput.value.trim()) {
            return true;
        }
        return isSavedSelectionActive(currentAddress);
    }

    function handleAddressInput() {
        const currentAddress = addressInput.value.trim();

        if (currentAddress !== selectedLabel) {
            tokenInput.value = "";
        }

        addressInput.setCustomValidity("");

        if (!currentAddress) {
            resetSuggestionsState();
            setStatus(enabled ? DEFAULT_STATUS : BLOCKED_STATUS);
            return;
        }

        if (!enabled || !suggestionsUrl) {
            resetSuggestionsState();
            setStatus(BLOCKED_STATUS);
            return;
        }

        if (isSavedSelectionActive(currentAddress)) {
            resetSuggestionsState();
            setStatus(SAVED_STATUS);
            return;
        }

        if (currentAddress.length < MIN_QUERY_LENGTH) {
            resetSuggestionsState();
            setStatus(DEFAULT_STATUS);
            return;
        }

        setStatus(LOOKUP_STATUS);
        window.clearTimeout(debounceId);
        debounceId = window.setTimeout(() => {
            fetchSuggestions(currentAddress);
        }, LOOKUP_DEBOUNCE_MS);
    }

    async function fetchSuggestions(query) {
        latestRequestId += 1;
        const requestId = latestRequestId;
        activeController?.abort();
        activeController = new AbortController();

        try {
            const url = new URL(suggestionsUrl, window.location.origin);
            url.searchParams.set("q", query);
            const response = await fetch(url, {
                headers: { Accept: "application/json" },
                signal: activeController.signal,
            });
            const payload = await response.json().catch(() => ({}));

            if (requestId !== latestRequestId) {
                return;
            }

            if (!response.ok) {
                clearSuggestions();
                setStatus(payload.error?.message || UNAVAILABLE_STATUS);
                return;
            }

            renderSuggestions(payload.results || []);
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            clearSuggestions();
            setStatus(UNAVAILABLE_STATUS);
        }
    }

    function renderSuggestions(results) {
        suggestionsNode.innerHTML = "";

        if (!results.length) {
            suggestionsNode.hidden = true;
            setStatus(EMPTY_RESULTS_STATUS);
            return;
        }

        results.forEach((result) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "list-group-item list-group-item-action";
            button.innerHTML = `
                <span class="d-block fw-semibold">${escapeHtml(result.label || "")}</span>
                <span class="d-block small text-muted">${escapeHtml(result.context_label || "")}</span>
            `;
            button.addEventListener("click", () => {
                addressInput.value = result.label || "";
                tokenInput.value = result.token || "";
                selectedLabel = addressInput.value.trim();
                addressInput.setCustomValidity("");
                clearSuggestions();
                setStatus(VERIFIED_STATUS);
            });
            suggestionsNode.append(button);
        });

        suggestionsNode.hidden = false;
        setStatus(CHOOSE_STATUS);
    }

    function handleSubmit(event) {
        const currentAddress = addressInput.value.trim();
        if (!currentAddress || isSelectionComplete()) {
            return;
        }

        event.preventDefault();
        const message = enabled ? SELECTION_REQUIRED_MESSAGE : BLOCKED_STATUS;
        addressInput.setCustomValidity(message);
        addressInput.reportValidity();
        addressInput.focus();
        setStatus(message);
    }

    function clearSuggestions() {
        suggestionsNode.innerHTML = "";
        suggestionsNode.hidden = true;
    }

    function resetSuggestionsState() {
        window.clearTimeout(debounceId);
        latestRequestId += 1;
        activeController?.abort();
        activeController = null;
        clearSuggestions();
    }

    function setStatus(message) {
        statusNode.textContent = message;
    }

    function isSavedSelectionActive(currentAddress) {
        return Boolean(savedSelectionLabel) && currentAddress === savedSelectionLabel;
    }
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
