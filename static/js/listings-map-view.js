function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function buildMarkerElement(markerData) {
    const element = document.createElement("button");
    element.type = "button";
    element.className = "listing-map-marker";
    element.innerHTML = `<span class="listing-map-marker-label">${escapeHtml(markerData.price)}</span>`;
    element.setAttribute("aria-label", `${markerData.title} ${markerData.price}`);
    element.setAttribute("aria-pressed", "false");
    return element;
}

function setMarkerSelectedState(element, isSelected) {
    element.classList.toggle("is-selected", isSelected);
    element.setAttribute("aria-pressed", isSelected ? "true" : "false");
}

export function createListingsMapView({
    root,
    styleUrl,
    defaultLat,
    defaultLng,
    initialMarkers = [],
    selectedListingId = "",
    onMarkerSelect,
    onViewportChange,
}) {
    const canvas = root?.querySelector("[data-listings-map-canvas]");

    if (!root || !canvas || !styleUrl || typeof maplibregl === "undefined") {
        return {
            getBounds() {
                return null;
            },
            setSelectedListing() {},
            renderMarkers() {},
        };
    }

    const map = new maplibregl.Map({
        container: canvas,
        style: styleUrl,
        center: [defaultLng, defaultLat],
        zoom: 12,
    });
    const markerEntries = new Map();
    let hasAppliedInitialViewport = false;
    let mapLoaded = false;
    let markers = Array.isArray(initialMarkers) ? initialMarkers : [];
    let activeListingId = selectedListingId ? String(selectedListingId) : "";

    const applySelection = () => {
        markerEntries.forEach((entry, listingId) => {
            setMarkerSelectedState(entry.element, listingId === activeListingId);
        });
    };

    const createMarkerEntry = (markerData) => {
        const listingId = String(markerData.id);
        const element = buildMarkerElement(markerData);
        element.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            activeListingId = listingId;
            applySelection();
            onMarkerSelect?.(markerData.id);
        });

        const marker = new maplibregl.Marker({
            anchor: "center",
            element,
        })
            .setLngLat([markerData.lng, markerData.lat])
            .addTo(map);

        markerEntries.set(listingId, { element, marker });
    };

    const syncMarkerEntries = () => {
        if (!mapLoaded) {
            return;
        }

        const nextMarkerIds = new Set();

        markers.forEach((markerData) => {
            const listingId = String(markerData.id);
            nextMarkerIds.add(listingId);

            const existingEntry = markerEntries.get(listingId);
            if (!existingEntry) {
                createMarkerEntry(markerData);
                return;
            }

            existingEntry.marker.setLngLat([markerData.lng, markerData.lat]);
            existingEntry.element.innerHTML = `<span class="listing-map-marker-label">${escapeHtml(markerData.price)}</span>`;
            existingEntry.element.setAttribute("aria-label", `${markerData.title} ${markerData.price}`);
        });

        markerEntries.forEach((entry, listingId) => {
            if (nextMarkerIds.has(listingId)) {
                return;
            }
            entry.marker.remove();
            markerEntries.delete(listingId);
        });

        applySelection();
        applyViewportToMarkers();
    };

    const applyViewportToMarkers = () => {
        if (hasAppliedInitialViewport || markers.length === 0) {
            return;
        }

        hasAppliedInitialViewport = true;

        if (markers.length === 1) {
            map.setCenter([markers[0].lng, markers[0].lat]);
            map.setZoom(13);
            return;
        }

        const bounds = new maplibregl.LngLatBounds();
        markers.forEach((marker) => {
            bounds.extend([marker.lng, marker.lat]);
        });
        map.fitBounds(bounds, { padding: 56, maxZoom: 14 });
    };

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
        mapLoaded = true;
        syncMarkerEntries();
    });
    map.on("moveend", () => {
        onViewportChange?.();
    });

    return {
        getBounds() {
            if (!mapLoaded) {
                return null;
            }

            const bounds = map.getBounds();
            return {
                west: bounds.getWest(),
                south: bounds.getSouth(),
                east: bounds.getEast(),
                north: bounds.getNorth(),
            };
        },
        renderMarkers(nextMarkers) {
            markers = Array.isArray(nextMarkers) ? nextMarkers : [];
            syncMarkerEntries();
        },
        setSelectedListing(listingId) {
            activeListingId = listingId ? String(listingId) : "";
            applySelection();
        },
    };
}
