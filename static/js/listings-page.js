import { createListingsMapView } from "./listings-map-view.js";
import { createListingsResults } from "./listings-results.js";

const LIVE_SEARCH_ERROR_MESSAGE = "Live search is temporarily unavailable. Showing the current listings.";
const SEARCH_DEBOUNCE_MS = 260;

function readJsonScript(id, fallback) {
    const node = document.getElementById(id);
    if (!node?.textContent) {
        return fallback;
    }

    try {
        return JSON.parse(node.textContent);
    } catch {
        return fallback;
    }
}

function buildSearchParams(form, bounds) {
    const params = new URLSearchParams();
    const formData = new FormData(form);

    for (const [key, value] of formData.entries()) {
        const normalizedValue = String(value || "").trim();
        if (normalizedValue) {
            params.set(key, normalizedValue);
        }
    }

    params.set("west", String(bounds.west));
    params.set("south", String(bounds.south));
    params.set("east", String(bounds.east));
    params.set("north", String(bounds.north));
    return params;
}

function currentQuery(form) {
    const query = form?.elements.namedItem("q");
    return query?.value?.trim() || "";
}

export function bootstrapListingsPage() {
    if (typeof document === "undefined") {
        return;
    }

    const root = document.querySelector("[data-listings-page]");
    if (!root) {
        return;
    }

    const form = root.querySelector("[data-listings-filter-form]");
    const mapRoot = root.querySelector("[data-listings-map-root]");
    const resultsRoot = root.querySelector("[data-listings-results]");
    const searchUrl = root.dataset.listingsSearchUrl || mapRoot?.dataset.listingsSearchUrl || "";
    const initialPayload = readJsonScript("listing-page-initial-payload", {
        total: 0,
        markers: [],
        cards: [],
    });
    const initialState = readJsonScript("listing-page-initial-state", {
        selected_listing_id: "",
        query: "",
    });

    if (!form || !mapRoot || !resultsRoot || !searchUrl) {
        return;
    }

    const resultsView = createListingsResults(resultsRoot);
    const state = {
        latestRequestId: 0,
        requestTimer: null,
        requestController: null,
        selectedListingId: initialState.selected_listing_id ? String(initialState.selected_listing_id) : "",
    };
    const mapView = createListingsMapView({
        root: mapRoot,
        styleUrl: root.dataset.listingsMapStyleUrl || mapRoot.dataset.listingsMapStyleUrl || "",
        defaultLat: Number(mapRoot.dataset.defaultLat || 42.3355),
        defaultLng: Number(mapRoot.dataset.defaultLng || -71.1685),
        initialMarkers: initialPayload.markers,
        selectedListingId: state.selectedListingId,
        onMarkerSelect(listingId) {
            state.selectedListingId = String(listingId);
            root.dataset.selectedListingId = state.selectedListingId;
            resultsView?.setSelectedListing(state.selectedListingId, { reveal: true });
            mapView.setSelectedListing(state.selectedListingId);
        },
        onViewportChange() {
            scheduleSearch();
        },
    });

    const syncSelection = (payload) => {
        const hasSelectedCard = payload.cards.some((card) => String(card.id) === state.selectedListingId);
        if (!hasSelectedCard) {
            state.selectedListingId = "";
            root.dataset.selectedListingId = "";
        }

        resultsView?.setSelectedListing(state.selectedListingId);
        mapView.setSelectedListing(state.selectedListingId);
    };

    const runSearch = async () => {
        const bounds = mapView.getBounds();
        if (!bounds) {
            return;
        }

        state.latestRequestId += 1;
        const requestId = state.latestRequestId;
        state.requestController?.abort();
        state.requestController = new AbortController();

        try {
            const response = await fetch(`${searchUrl}?${buildSearchParams(form, bounds).toString()}`, {
                headers: {
                    Accept: "application/json",
                },
                signal: state.requestController.signal,
            });

            if (!response.ok) {
                throw new Error(`Search failed with status ${response.status}`);
            }

            const payload = await response.json();
            if (requestId !== state.latestRequestId) {
                return;
            }

            resultsView?.clearError();
            resultsView?.render(payload, { query: currentQuery(form) });
            resultsView?.hidePagination();
            mapView.renderMarkers(payload.markers);
            syncSelection(payload);
        } catch (error) {
            if (error.name === "AbortError" || requestId !== state.latestRequestId) {
                return;
            }

            resultsView?.showError(LIVE_SEARCH_ERROR_MESSAGE);
        }
    };

    const scheduleSearch = (delay = SEARCH_DEBOUNCE_MS) => {
        if (state.requestTimer) {
            window.clearTimeout(state.requestTimer);
        }
        state.requestTimer = window.setTimeout(() => {
            runSearch();
        }, delay);
    };

    root.dataset.selectedListingId = state.selectedListingId;
    resultsView?.setSelectedListing(state.selectedListingId);

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        scheduleSearch(0);
    });
    form.addEventListener("input", () => {
        scheduleSearch();
    });
    form.addEventListener("change", () => {
        scheduleSearch();
    });
}
