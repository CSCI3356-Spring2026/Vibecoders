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

function getCookie(name) {
    if (typeof document === "undefined") {
        return "";
    }

    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (const cookie of cookies) {
        const trimmed = cookie.trim();
        if (trimmed.startsWith(`${name}=`)) {
            return decodeURIComponent(trimmed.slice(name.length + 1));
        }
    }
    return "";
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

function buildFavoriteForm(card, csrfToken, nextUrl) {
    if (!card.favorite_url) {
        return "";
    }

    const label = card.is_favorited ? "Saved" : "Save";
    const pressed = card.is_favorited ? "true" : "false";
    const favoritedClass = card.is_favorited ? " is-favorited" : "";

    return `
        <form class="listing-favorite-form" method="post" action="${escapeHtml(card.favorite_url)}">
            <input type="hidden" name="csrfmiddlewaretoken" value="${escapeHtml(csrfToken)}">
            <input type="hidden" name="next" value="${escapeHtml(nextUrl)}">
            <button
                class="listing-favorite-button${favoritedClass}"
                type="submit"
                data-favorite-button
                aria-pressed="${pressed}"
                aria-label="${card.is_favorited ? "Remove saved listing" : "Save listing"}"
            >
                <span class="listing-favorite-button-icon" aria-hidden="true"></span>
                <span class="listing-favorite-button-label">${escapeHtml(label)}</span>
            </button>
        </form>
    `;
}

function buildCardMarkup(card, { csrfToken, nextUrl }) {
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
    const verifiedBadge = card.is_verified ? '<span class="listing-card-verified">Verified</span>' : "";
    const ratingMarkup =
        card.review_count > 0 && card.average_rating !== null
            ? `<span class="listing-card-rating">${escapeHtml(card.average_rating)} ★ · ${escapeHtml(card.review_count)} review${pluralize(card.review_count)}</span>`
            : "";

    return `
        <div class="listing-card-shell">
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
                </div>
                <div class="listing-card-body">
                    <div class="listing-card-topline">
                        <div class="listing-card-badges">
                            ${verifiedBadge}
                            <span class="listing-card-badge">${escapeHtml(card.lease_type)}</span>
                            <span class="listing-card-chip">${escapeHtml(card.property_type)}</span>
                        </div>
                        <span class="listing-card-status is-${escapeHtml(card.status.state)}">${escapeHtml(card.status.label)}</span>
                    </div>
                    <div class="listing-card-price-row">
                        <span class="listing-card-price">${escapeHtml(card.price)}</span>
                        ${ratingMarkup}
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
            ${buildFavoriteForm(card, csrfToken, nextUrl)}
        </div>
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

    const handleCardClick = (event) => {
        const card = event.target.closest("[data-listing-card]");
        if (!card || !list?.contains(card) || event.defaultPrevented) {
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
    list?.addEventListener("click", handleCardClick);

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
            const csrfToken = list?.dataset.favoriteCsrfToken || getCookie("csrftoken") || "";
            const nextUrl = list?.dataset.favoriteNextUrl || window.location.href;

            if (list) {
                list.innerHTML = cards.map((card) => buildCardMarkup(card, { csrfToken, nextUrl })).join("");
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
