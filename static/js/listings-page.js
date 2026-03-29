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
    const mapStyleToggles = Array.from(root.querySelectorAll("[data-listings-map-style-toggle]"));
    const searchUrl = root.dataset.listingsSearchUrl || mapRoot?.dataset.listingsSearchUrl || "";
    const defaultMapStyleUrl =
        root.dataset.listingsMapDefaultStyleUrl ||
        root.dataset.listingsMapStyleUrl ||
        mapRoot?.dataset.listingsMapDefaultStyleUrl ||
        mapRoot?.dataset.listingsMapStyleUrl ||
        "";
    const satelliteMapStyleUrl =
        root.dataset.listingsMapSatelliteStyleUrl || mapRoot?.dataset.listingsMapSatelliteStyleUrl || "";
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
        defaultStyleUrl: defaultMapStyleUrl,
        satelliteStyleUrl: satelliteMapStyleUrl,
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

    const syncStyleToggleState = (mode) => {
        mapStyleToggles.forEach((button) => {
            const isActive = button.dataset.styleMode === mode;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
    };

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
    syncStyleToggleState(mapView.getStyleMode());

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

    mapStyleToggles.forEach((button) => {
        button.addEventListener("click", () => {
            const nextMode = button.dataset.styleMode || "map";
            mapView.setStyleMode(nextMode);
            syncStyleToggleState(mapView.getStyleMode());
        });
    });
}
