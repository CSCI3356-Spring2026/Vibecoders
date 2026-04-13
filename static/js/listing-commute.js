const payloadElement = document.getElementById("listing-commute-payload");
const root = document.querySelector("[data-listing-commute]");

const ROUTING_MODES = {
    walking: "walk",
    transit: "transit",
    driving: "drive",
};

function formatRouteDuration(seconds) {
    const totalMinutes = Math.max(1, Math.round(Number(seconds || 0) / 60));
    if (totalMinutes < 60) {
        return `${totalMinutes} min`;
    }

    const hours = Math.floor(totalMinutes / 60);
    const minutes = totalMinutes % 60;
    return minutes ? `${hours} hr ${minutes} min` : `${hours} hr`;
}

function midpoint(origin, destination) {
    return [
        (Number(origin.lng) + Number(destination.lng)) / 2,
        (Number(origin.lat) + Number(destination.lat)) / 2,
    ];
}

function createCommuteMap({ map: mapConfig, origin, destination }, mapElement, noteElement) {
    if (!mapConfig?.style_url || !origin || !destination || typeof maplibregl === "undefined" || !mapElement) {
        return null;
    }

    const routeSourceId = "listing-commute-route";
    let currentRouteData = {
        type: "FeatureCollection",
        features: [],
    };

    const map = new maplibregl.Map({
        container: mapElement,
        style: mapConfig.style_url,
        center: midpoint(origin, destination),
        zoom: 12,
        attributionControl: false,
    });

    const buildMarker = (color) =>
        new maplibregl.Marker({
            color,
            scale: 0.85,
        });

    buildMarker("#d9392e").setLngLat([origin.lng, origin.lat]).addTo(map);
    buildMarker("#1761c2").setLngLat([destination.lng, destination.lat]).addTo(map);

    const applyViewport = () => {
        const bounds = new maplibregl.LngLatBounds();
        bounds.extend([origin.lng, origin.lat]);
        bounds.extend([destination.lng, destination.lat]);
        map.fitBounds(bounds, { padding: 36, maxZoom: 13, duration: 0 });
    };

    const ensureRouteLayer = () => {
        if (!map.getSource(routeSourceId)) {
            map.addSource(routeSourceId, {
                type: "geojson",
                data: currentRouteData,
            });
        }

        if (!map.getLayer(routeSourceId)) {
            map.addLayer({
                id: routeSourceId,
                type: "line",
                source: routeSourceId,
                layout: {
                    "line-cap": "round",
                    "line-join": "round",
                },
                paint: {
                    "line-color": "#d9392e",
                    "line-width": 4,
                    "line-opacity": 0.9,
                },
            });
        }
    };

    map.on("load", () => {
        ensureRouteLayer();
        applyViewport();
    });
    map.on("style.load", () => {
        ensureRouteLayer();
        map.getSource(routeSourceId)?.setData(currentRouteData);
        applyViewport();
    });

    return {
        async renderRoute(modeValue) {
            const routeMode = ROUTING_MODES[modeValue];
            if (!routeMode) {
                if (noteElement) {
                    noteElement.textContent = "Route preview unavailable for this travel mode.";
                }
                return null;
            }

            if (noteElement) {
                noteElement.textContent = "Loading route map.";
            }

            const params = new URLSearchParams({
                waypoints: `${origin.lat},${origin.lng}|${destination.lat},${destination.lng}`,
                mode: routeMode,
                format: "geojson",
                apiKey: mapConfig.api_key,
            });
            const response = await fetch(`${mapConfig.routing_url}?${params.toString()}`);
            if (!response.ok) {
                throw new Error(`Routing request failed with status ${response.status}`);
            }

            const routePayload = await response.json();
            const feature = routePayload?.features?.[0];
            if (!feature?.geometry) {
                throw new Error("Routing payload did not include geometry.");
            }

            currentRouteData = {
                type: "FeatureCollection",
                features: [feature],
            };
            map.getSource(routeSourceId)?.setData(currentRouteData);
            applyViewport();

            if (noteElement) {
                noteElement.textContent = "Route to Boston College.";
            }

            return feature.properties || {};
        },
    };
}

if (payloadElement && root) {
    const payload = JSON.parse(payloadElement.textContent || "{}");
    const modeSelect = root.querySelector("[data-commute-mode-select]");
    const minutesValue = root.querySelector("[data-commute-minutes]");
    const mapElement = root.querySelector("[data-commute-map]");
    const mapNote = root.querySelector("[data-commute-map-note]");
    const modes = new Map((payload.modes || []).map((mode) => [mode.value, mode]));
    const commuteMap = createCommuteMap(payload, mapElement, mapNote);
    let activeRequestId = 0;

    const setMinutes = (value) => {
        if (minutesValue) {
            minutesValue.textContent = value || "Unavailable";
        }
    };

    const applyMode = async (modeValue) => {
        const selectedMode = modes.get(modeValue) || modes.get(payload.default_mode);
        if (!selectedMode) {
            return;
        }

        setMinutes(selectedMode.display);
        if (!commuteMap) {
            return;
        }

        activeRequestId += 1;
        const requestId = activeRequestId;

        try {
            const route = await commuteMap.renderRoute(selectedMode.value);
            if (requestId !== activeRequestId) {
                return;
            }

            if (route?.time) {
                setMinutes(formatRouteDuration(route.time));
            }
        } catch {
            if (requestId !== activeRequestId) {
                return;
            }

            if (mapNote) {
                mapNote.textContent = "Live route data is unavailable right now. Showing the estimate above.";
            }
        }
    };

    if (modeSelect instanceof HTMLSelectElement) {
        applyMode(modeSelect.value || payload.default_mode);
        modeSelect.addEventListener("change", () => {
            applyMode(modeSelect.value);
        });
    }
}
