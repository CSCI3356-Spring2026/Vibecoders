import { createListingsMapView } from "./listings-map-view.js";
import { createListingsResults } from "./listings-results.js";

const LIVE_SEARCH_ERROR_MESSAGE = "Live search is temporarily unavailable. Showing the current listings.";
const SEARCH_DEBOUNCE_MS = 260;
const currencyFormatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
});
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

function buildSearchParams(form, bounds, { includeViewport = true } = {}) {
    const params = new URLSearchParams();
    const formData = new FormData(form);

    for (const [key, value] of formData.entries()) {
        const normalizedValue = String(value || "").trim();
        if (normalizedValue) {
            params.set(key, normalizedValue);
        }
    }

    if (includeViewport && bounds) {
        params.set("west", String(bounds.west));
        params.set("south", String(bounds.south));
        params.set("east", String(bounds.east));
        params.set("north", String(bounds.north));
    }
    return params;
}

function currentQuery(form) {
    const query = form?.elements.namedItem("q");
    return query?.value?.trim() || "";
}

function getFormControl(form, name) {
    if (!form?.elements) {
        return null;
    }

    const control = form.elements.namedItem(name);
    if (!control) {
        return null;
    }

    if (typeof RadioNodeList !== "undefined" && control instanceof RadioNodeList) {
        return control[0] ?? null;
    }

    return control;
}

function parseNumericValue(rawValue) {
    const normalizedValue = String(rawValue ?? "").trim();
    if (!normalizedValue) {
        return null;
    }

    const parsed = Number(normalizedValue);
    return Number.isFinite(parsed) ? parsed : null;
}

function formatMoney(value) {
    return currencyFormatter.format(value);
}

function createListingsFilterToolbar(root, form) {
    const filterMenus = Array.from(root.querySelectorAll("[data-listings-filter-menu]"));
    if (!filterMenus.length) {
        return null;
    }

    const menusByName = Object.fromEntries(
        filterMenus
            .map((menu) => [menu.dataset.filterName || "", menu])
            .filter(([name]) => Boolean(name)),
    );
    const summaryNodes = Object.fromEntries(
        Array.from(root.querySelectorAll("[data-listings-filter-summary]")).map((node) => [node.dataset.listingsFilterSummary, node]),
    );

    const minPriceField = getFormControl(form, "min_price");
    const maxPriceField = getFormControl(form, "max_price");
    const minBedroomsControl = getFormControl(form, "min_bedrooms");
    const minBathroomsControl = getFormControl(form, "min_bathrooms");
    const leaseControl = getFormControl(form, "lease_type");
    const propertyTypeControl = getFormControl(form, "property_type");
    const spaceTypeControl = getFormControl(form, "space_type");
    const queryControl = getFormControl(form, "q");
    const maxUpfrontControl = getFormControl(form, "max_upfront");
    const maxDistanceControl = getFormControl(form, "max_distance");
    const availabilityStartControl = getFormControl(form, "availability_start");
    const availabilityEndControl = getFormControl(form, "availability_end");
    const savedControl = getFormControl(form, "saved");
    const featureControls = [
        getFormControl(form, "has_parking"),
        getFormControl(form, "is_furnished"),
        getFormControl(form, "allows_pets"),
        getFormControl(form, "has_yard"),
        getFormControl(form, "no_stairs"),
        getFormControl(form, "landlord_approval_required"),
    ].filter(Boolean);

    const closeMenus = (exceptMenu = null) => {
        filterMenus.forEach((menu) => {
            if (menu !== exceptMenu) {
                menu.open = false;
            }
        });
    };

    const normalizePriceBounds = (changedName = "") => {
        const minPrice = parseNumericValue(minPriceField?.value);
        const maxPrice = parseNumericValue(maxPriceField?.value);

        if (minPrice === null || maxPrice === null || minPrice <= maxPrice) {
            return;
        }

        if (changedName === "max_price") {
            if (minPriceField) {
                minPriceField.value = maxPriceField?.value || "";
            }
            return;
        }

        if (maxPriceField) {
            maxPriceField.value = minPriceField?.value || "";
        }
    };

    const selectedOptionText = (control) => control?.options?.[control.selectedIndex]?.textContent?.trim() || "";
    const checkedFeatures = () =>
        featureControls.filter((control) => control.checked).map((control) => control.parentElement?.textContent?.trim() || "");

    const syncSummaries = () => {
        const minPrice = parseNumericValue(minPriceField?.value);
        const maxPrice = parseNumericValue(maxPriceField?.value);
        const priceSummary =
            minPrice !== null && maxPrice !== null
                ? `${formatMoney(minPrice)} - ${formatMoney(maxPrice)}`
                : minPrice !== null
                  ? `${formatMoney(minPrice)}+`
                  : maxPrice !== null
                    ? `Up to ${formatMoney(maxPrice)}`
                    : "Any price";
        if (summaryNodes.price) {
            summaryNodes.price.textContent = priceSummary;
        }
        menusByName.price?.classList.toggle("is-active", minPrice !== null || maxPrice !== null);

        const bedsActive = Boolean(minBedroomsControl?.value);
        if (summaryNodes.beds) {
            summaryNodes.beds.textContent = bedsActive ? selectedOptionText(minBedroomsControl) : "Any beds";
        }
        menusByName.beds?.classList.toggle("is-active", bedsActive);

        const bathsActive = Boolean(minBathroomsControl?.value);
        if (summaryNodes.baths) {
            summaryNodes.baths.textContent = bathsActive ? selectedOptionText(minBathroomsControl) : "Any baths";
        }
        menusByName.baths?.classList.toggle("is-active", bathsActive);

        const leaseActive = Boolean(leaseControl?.value);
        if (summaryNodes.lease) {
            summaryNodes.lease.textContent = leaseActive ? selectedOptionText(leaseControl) : "Any type";
        }
        menusByName.lease?.classList.toggle("is-active", leaseActive);

        const startDate = availabilityStartControl?.value || "";
        const endDate = availabilityEndControl?.value || "";
        const savedActive = Boolean(savedControl?.value);
        const features = checkedFeatures();
        let extraFilterCount = 0;
        if (queryControl?.value?.trim()) {
            extraFilterCount += 1;
        }
        if (maxDistanceControl?.value) {
            extraFilterCount += 1;
        }
        if (maxUpfrontControl?.value) {
            extraFilterCount += 1;
        }
        if (propertyTypeControl?.value) {
            extraFilterCount += 1;
        }
        if (spaceTypeControl?.value) {
            extraFilterCount += 1;
        }
        if (startDate || endDate) {
            extraFilterCount += 1;
        }
        if (savedActive) {
            extraFilterCount += 1;
        }
        if (features.length > 0) {
            extraFilterCount += 1;
        }

        if (summaryNodes.filters) {
            summaryNodes.filters.textContent = extraFilterCount ? `${extraFilterCount} active` : "More";
        }
        menusByName.filters?.classList.toggle("is-active", extraFilterCount > 0);
    };

    filterMenus.forEach((menu) => {
        menu.addEventListener("toggle", () => {
            if (menu.open) {
                closeMenus(menu);
            }
        });
    });

    document.addEventListener("click", (event) => {
        if (!root.contains(event.target) || !event.target.closest("[data-listings-filter-menu]")) {
            closeMenus();
        }
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeMenus();
        }
    });

    syncSummaries();

    return {
        sync() {
            normalizePriceBounds();
            syncSummaries();
        },
        handleChange(event) {
            normalizePriceBounds(event.target?.name || "");
            const menu = event.target.closest("[data-listings-filter-menu]");
            if (menu && event.target.tagName === "SELECT") {
                menu.open = false;
            }
            syncSummaries();
        },
        handleInput() {
            syncSummaries();
        },
    };
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
    const resultsUrl = root.dataset.listingsResultsUrl || "";
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
    });
    const initialState = readJsonScript("listing-page-initial-state", {
        selected_listing_id: "",
        query: "",
    });

    if (!form || !mapRoot || !resultsRoot || !searchUrl || !resultsUrl) {
        return;
    }

    const resultsView = createListingsResults(resultsRoot);
    const filterToolbar = createListingsFilterToolbar(root, form);
    const state = {
        latestMarkerRequestId: 0,
        latestResultsRequestId: 0,
        requestTimer: null,
        markerRequestController: null,
        resultsRequestController: null,
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
            scheduleMarkerRefresh();
        },
    });

    const syncStyleToggleState = (mode) => {
        mapStyleToggles.forEach((button) => {
            const isActive = button.dataset.styleMode === mode;
            button.classList.toggle("is-active", isActive);
            button.setAttribute("aria-pressed", isActive ? "true" : "false");
        });
    };

    const syncSelection = () => {
        const hasSelectedCard =
            state.selectedListingId &&
            resultsRoot.querySelector(`[data-listing-card][data-listing-id="${state.selectedListingId}"]`);
        if (!hasSelectedCard) {
            state.selectedListingId = "";
            root.dataset.selectedListingId = "";
        }

        resultsView?.setSelectedListing(state.selectedListingId);
        mapView.setSelectedListing(state.selectedListingId);
    };

    const runMarkerSearch = async () => {
        const bounds = mapView.getBounds();
        if (!bounds) {
            return;
        }

        state.latestMarkerRequestId += 1;
        const requestId = state.latestMarkerRequestId;
        state.markerRequestController?.abort();
        state.markerRequestController = new AbortController();

        try {
            const response = await fetch(`${searchUrl}?${buildSearchParams(form, bounds).toString()}`, {
                headers: {
                    Accept: "application/json",
                },
                signal: state.markerRequestController.signal,
            });

            if (!response.ok) {
                throw new Error(`Search failed with status ${response.status}`);
            }

            const payload = await response.json();
            if (requestId !== state.latestMarkerRequestId) {
                return;
            }

            resultsView?.clearError();
            mapView.renderMarkers(payload.markers);
            syncSelection();
        } catch (error) {
            if (error.name === "AbortError" || requestId !== state.latestMarkerRequestId) {
                return;
            }

            resultsView?.showError(LIVE_SEARCH_ERROR_MESSAGE);
        }
    };

    const runResultsSearch = async (targetUrl = "") => {
        state.latestResultsRequestId += 1;
        const requestId = state.latestResultsRequestId;
        state.resultsRequestController?.abort();
        state.resultsRequestController = new AbortController();

        const requestUrl = targetUrl || `${resultsUrl}?${buildSearchParams(form, null, { includeViewport: false }).toString()}`;

        try {
            const response = await fetch(requestUrl, {
                headers: {
                    Accept: "text/html",
                },
                signal: state.resultsRequestController.signal,
            });
            if (!response.ok) {
                throw new Error(`Results failed with status ${response.status}`);
            }

            const html = await response.text();
            if (requestId !== state.latestResultsRequestId) {
                return;
            }

            resultsView?.clearError();
            resultsView?.replaceContent(html);
            syncSelection();
        } catch (error) {
            if (error.name === "AbortError" || requestId !== state.latestResultsRequestId) {
                return;
            }
            resultsView?.showError(LIVE_SEARCH_ERROR_MESSAGE);
        }
    };

    const scheduleFilterRefresh = (delay = SEARCH_DEBOUNCE_MS) => {
        if (state.requestTimer) {
            window.clearTimeout(state.requestTimer);
        }
        state.requestTimer = window.setTimeout(() => {
            void Promise.all([runMarkerSearch(), runResultsSearch()]);
        }, delay);
    };

    const scheduleMarkerRefresh = (delay = SEARCH_DEBOUNCE_MS) => {
        if (state.requestTimer) {
            window.clearTimeout(state.requestTimer);
        }
        state.requestTimer = window.setTimeout(() => {
            void runMarkerSearch();
        }, delay);
    };

    root.dataset.selectedListingId = state.selectedListingId;
    resultsView?.setSelectedListing(state.selectedListingId);
    syncStyleToggleState(mapView.getStyleMode());
    filterToolbar?.sync();

    form.addEventListener("submit", (event) => {
        event.preventDefault();
        scheduleFilterRefresh(0);
    });
    form.addEventListener("input", (event) => {
        filterToolbar?.handleInput(event);
        scheduleFilterRefresh();
    });
    form.addEventListener("change", (event) => {
        filterToolbar?.handleChange(event);
        scheduleFilterRefresh();
    });
    resultsRoot.addEventListener("click", (event) => {
        const href = resultsView?.paginationHrefForEvent(event);
        if (!href) {
            return;
        }
        event.preventDefault();
        void runResultsSearch(href);
    });

    mapStyleToggles.forEach((button) => {
        button.addEventListener("click", () => {
            const nextMode = button.dataset.styleMode || "map";
            mapView.setStyleMode(nextMode);
            syncStyleToggleState(mapView.getStyleMode());
        });
    });
}
