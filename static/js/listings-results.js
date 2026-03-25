function pluralize(count) {
    return count === 1 ? "" : "s";
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function buildInitials(name) {
    return String(name || "")
        .trim()
        .split(/\s+/)
        .slice(0, 2)
        .map((part) => part.charAt(0).toUpperCase())
        .join("") || "?";
}

function buildOwnerAvatar(card) {
    if (card.owner_avatar_url) {
        return `
            <span class="user-avatar user-avatar-sm listing-card-owner-avatar">
                <img
                    class="user-avatar-image"
                    src="${escapeHtml(card.owner_avatar_url)}"
                    alt="${escapeHtml(card.owner_name)}"
                >
            </span>
        `;
    }

    return `
        <span class="user-avatar user-avatar-sm listing-card-owner-avatar">
            <span class="user-avatar-fallback">${escapeHtml(buildInitials(card.owner_name))}</span>
        </span>
    `;
}

function buildCardMarkup(card) {
    const specs = [
        `<span>${escapeHtml(card.rooms)} bd</span>`,
        `<span>${escapeHtml(card.bathrooms)} ba</span>`,
    ];

    if (card.sq_ft) {
        specs.push(`<span>${escapeHtml(card.sq_ft)} sqft</span>`);
    }

    const media = card.image_url
        ? `<img src="${escapeHtml(card.image_url)}" alt="${escapeHtml(card.title)}">`
        : `
            <div class="listing-card-placeholder">
                <span>${escapeHtml(card.property_type)}</span>
            </div>
        `;

    const summary = card.description
        ? `<p class="listing-card-summary">${escapeHtml(card.description)}</p>`
        : "";

    return `
        <a
            class="listing-card"
            href="${escapeHtml(card.url)}"
            data-listing-card
            data-listing-id="${escapeHtml(card.id)}"
            data-listing-detail-url="${escapeHtml(card.url)}"
            data-listing-selected="false"
        >
            <div class="listing-card-media">
                ${media}
                <div class="listing-card-badge">${escapeHtml(card.lease_type)}</div>
            </div>
            <div class="listing-card-body">
                <div class="listing-card-price-row">
                    <span class="listing-card-price">${escapeHtml(card.price)}</span>
                    <span class="listing-card-status is-${escapeHtml(card.status.state)}">${escapeHtml(card.status.label)}</span>
                </div>
                <h3 class="listing-card-title">${escapeHtml(card.title)}</h3>
                <p class="listing-card-address">${escapeHtml(card.address)}</p>
                <div class="listing-card-specs">${specs.join("")}</div>
                ${summary}
                <div class="listing-card-owner">
                    <div class="listing-owner-meta">
                        ${buildOwnerAvatar(card)}
                        <div class="listing-owner-copy">
                            <span class="listing-owner-label">Posted by</span>
                            <span class="listing-owner-name">${escapeHtml(card.owner_name || "Listing owner")}</span>
                        </div>
                    </div>
                </div>
            </div>
        </a>
    `;
}

export function createListingsResults(root) {
    if (!root) {
        return null;
    }

    const summary = root.querySelector("[data-listings-results-summary]");
    const error = root.querySelector("[data-listings-live-error]");
    const list = root.querySelector("[data-listings-results-list]");
    const emptyState = root.querySelector("[data-listings-empty-state]");
    const pagination = root.querySelector("[data-listings-pagination]");
    let selectedListingId = "";
    let cardElementsById = new Map();

    const reindexCards = () => {
        cardElementsById = new Map();
        list?.querySelectorAll("[data-listing-card]").forEach((card) => {
            if (card.dataset.listingId) {
                cardElementsById.set(card.dataset.listingId, card);
            }
        });
    };

    const setSummary = ({ total, query }) => {
        if (!summary) {
            return;
        }

        const trimmedQuery = String(query || "").trim();
        summary.textContent = trimmedQuery
            ? `${total} result${pluralize(total)} for "${trimmedQuery}".`
            : `${total} result${pluralize(total)}.`;
    };

    const setEmptyState = (isEmpty) => {
        if (list) {
            list.hidden = isEmpty;
        }
        if (emptyState) {
            emptyState.hidden = !isEmpty;
        }
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

    reindexCards();

    return {
        clearError() {
            if (!error) {
                return;
            }
            error.hidden = true;
            error.textContent = "";
        },
        hidePagination() {
            if (pagination) {
                pagination.hidden = true;
            }
        },
        render(payload, state = {}) {
            const cards = Array.isArray(payload?.cards) ? payload.cards : [];

            if (list) {
                list.innerHTML = cards.map((card) => buildCardMarkup(card)).join("");
            }

            reindexCards();
            setSummary({
                total: Number(payload?.total || 0),
                query: state.query,
            });
            setEmptyState(cards.length === 0);
            applySelection(selectedListingId);
        },
        setSelectedListing(listingId, options) {
            applySelection(listingId, options);
        },
        showError(message) {
            if (!error) {
                return;
            }
            error.hidden = false;
            error.textContent = message;
        },
    };
}
