export function createListingsResults(root) {
    if (!root) {
        return null;
    }

    let selectedListingId = "";
    let cardElementsById = new Map();

    const reindexCards = () => {
        cardElementsById = new Map();
        root.querySelectorAll("[data-listing-card]").forEach((card) => {
            if (card.dataset.listingId) {
                cardElementsById.set(card.dataset.listingId, card);
            }
        });
    };

    const applySelection = (listingId, { reveal = false } = {}) => {
        selectedListingId = listingId ? String(listingId) : "";

        cardElementsById.forEach((card, cardId) => {
            card.dataset.listingSelected = cardId === selectedListingId ? "true" : "false";
        });

        if (!reveal || !selectedListingId) {
            return;
        }

        const selectedCard = cardElementsById.get(selectedListingId);
        selectedCard?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
    };

    const handleCardClick = (event) => {
        const card = event.target.closest("[data-listing-card]");
        if (!card || !root.contains(card) || event.defaultPrevented) {
            return;
        }

        const detailUrl = card.dataset.listingDetailUrl || card.getAttribute("href");
        const isPlainLeftClick =
            event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;

        if (!detailUrl || !isPlainLeftClick) {
            return;
        }

        event.preventDefault();
        window.location.assign(detailUrl);
    };

    root.addEventListener("click", handleCardClick);
    reindexCards();

    return {
        clearError() {
            const error = root.querySelector("[data-listings-live-error]");
            if (!error) {
                return;
            }
            error.hidden = true;
            error.textContent = "";
        },
        paginationHrefForEvent(event) {
            const link = event.target.closest("[data-listings-pagination] a[href]");
            if (!link || !root.contains(link)) {
                return "";
            }
            return link.href || "";
        },
        replaceContent(html) {
            const currentContent = root.querySelector("[data-listings-results-content]");
            if (!currentContent) {
                return;
            }

            currentContent.outerHTML = html;
            reindexCards();
            applySelection(selectedListingId);
        },
        setSelectedListing(listingId, options) {
            applySelection(listingId, options);
        },
        showError(message) {
            const error = root.querySelector("[data-listings-live-error]");
            if (!error) {
                return;
            }
            error.hidden = false;
            error.textContent = message;
        },
    };
}
