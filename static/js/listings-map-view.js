function setMarkerStyles(element, isSelected) {
    element.dataset.markerSelected = isSelected ? "true" : "false";
    element.style.alignItems = "center";
    element.style.appearance = "none";
    element.style.background = isSelected ? "#1f4d67" : "rgba(255, 255, 255, 0.97)";
    element.style.border = isSelected ? "1px solid #1f4d67" : "1px solid rgba(22, 33, 43, 0.18)";
    element.style.borderRadius = "999px";
    element.style.boxShadow = isSelected
        ? "0 12px 24px rgba(31, 77, 103, 0.22)"
        : "0 10px 22px rgba(22, 33, 43, 0.14)";
    element.style.color = isSelected ? "#ffffff" : "#16212b";
    element.style.cursor = "pointer";
    element.style.display = "inline-flex";
    element.style.fontFamily = '"Instrument Sans", sans-serif';
    element.style.fontSize = "0.78rem";
    element.style.fontWeight = "700";
    element.style.justifyContent = "center";
    element.style.letterSpacing = "0.01em";
    element.style.minHeight = "2.15rem";
    element.style.minWidth = "3.35rem";
    element.style.padding = "0.35rem 0.65rem";
    element.style.transform = isSelected ? "translateY(-1px) scale(1.03)" : "translateY(0) scale(1)";
    element.style.transition = "transform 140ms ease, box-shadow 140ms ease, background-color 140ms ease";
    element.style.whiteSpace = "nowrap";
    element.style.zIndex = isSelected ? "2" : "1";
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
            setMarkerStyles(entry.element, listingId === activeListingId);
        });
    };

    const clearMarkers = () => {
        markerEntries.forEach((entry) => entry.marker.remove());
        markerEntries.clear();
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

    const drawMarkers = () => {
        if (!mapLoaded) {
            return;
        }

        clearMarkers();

        markers.forEach((markerData) => {
            const element = document.createElement("button");
            element.type = "button";
            element.textContent = markerData.price;
            element.setAttribute("aria-label", `${markerData.title} ${markerData.price}`);
            setMarkerStyles(element, false);
            element.addEventListener("click", (event) => {
                event.preventDefault();
                event.stopPropagation();
                activeListingId = String(markerData.id);
                applySelection();
                onMarkerSelect?.(markerData.id);
            });

            const marker = new maplibregl.Marker({
                anchor: "center",
                element,
            })
                .setLngLat([markerData.lng, markerData.lat])
                .addTo(map);

            markerEntries.set(String(markerData.id), { element, marker });
        });

        applySelection();
        applyViewportToMarkers();
    };

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
        mapLoaded = true;
        drawMarkers();
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
            drawMarkers();
        },
        setSelectedListing(listingId) {
            activeListingId = listingId ? String(listingId) : "";
            applySelection();
        },
    };
}
