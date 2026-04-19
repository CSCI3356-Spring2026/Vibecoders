const payloadElement = document.getElementById("listing-commute-config");
const root = document.querySelector("[data-listing-commute]");

function createCommuteMap(mapConfig, mapElement) {
    if (!mapConfig?.style_url || typeof maplibregl === "undefined" || !mapElement) {
        return null;
    }

    const routeSourceId = "listing-commute-route";
    let currentRouteData = {
        type: "FeatureCollection",
        features: [],
    };
    let markersAdded = false;

    const map = new maplibregl.Map({
        container: mapElement,
        style: mapConfig.style_url,
        center: [-71.1685, 42.3355],
        zoom: 12,
        attributionControl: false,
    });

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

    map.on("load", ensureRouteLayer);
    map.on("style.load", () => {
        ensureRouteLayer();
        map.getSource(routeSourceId)?.setData(currentRouteData);
    });

    return {
        renderRoute(routeGeometry, origin, destination) {
            currentRouteData = {
                type: "FeatureCollection",
                features: routeGeometry
                    ? [
                          {
                              type: "Feature",
                              geometry: routeGeometry,
                              properties: {},
                          },
                      ]
                    : [],
            };
            map.getSource(routeSourceId)?.setData(currentRouteData);

            if (!markersAdded && origin && destination) {
                new maplibregl.Marker({ color: "#d9392e", scale: 0.85 })
                    .setLngLat([origin.lng, origin.lat])
                    .addTo(map);
                new maplibregl.Marker({ color: "#1761c2", scale: 0.85 })
                    .setLngLat([destination.lng, destination.lat])
                    .addTo(map);
                markersAdded = true;
            }

            const bounds = new maplibregl.LngLatBounds();
            bounds.extend([origin.lng, origin.lat]);
            bounds.extend([destination.lng, destination.lat]);
            map.fitBounds(bounds, { padding: 36, maxZoom: 13, duration: 0 });

        },
    };
}

if (payloadElement && root) {
    const config = JSON.parse(payloadElement.textContent || "{}");
    const modeSelect = root.querySelector("[data-commute-mode-select]");
    const minutesValue = root.querySelector("[data-commute-minutes]");
    const distanceValue = root.querySelector("[data-commute-distance]");
    const mapElement = root.querySelector("[data-commute-map]");
    const mapNote = root.querySelector("[data-commute-map-note]");
    const commuteMap = createCommuteMap(config.map, mapElement);
    let payload = null;

    const setMapNote = (message, { hidden = false } = {}) => {
        if (!mapNote) {
            return;
        }
        mapNote.textContent = message;
        mapNote.hidden = hidden;
    };

    const setUnavailable = (message) => {
        if (minutesValue) {
            minutesValue.textContent = "Unavailable";
        }
        if (distanceValue) {
            distanceValue.textContent = "Unavailable";
        }
        setMapNote(message);
    };

    const applyMode = (modeValue) => {
        const route = payload?.routes?.[modeValue] || payload?.routes?.[payload?.default_mode];
        if (!route) {
            setUnavailable("Route-backed commute is unavailable right now.");
            return;
        }

        if (minutesValue) {
            minutesValue.textContent = route.display || "Unavailable";
        }
        if (distanceValue) {
            distanceValue.textContent = route.distance_miles ? `${route.distance_miles} mi` : "Unavailable";
        }
        setMapNote("", { hidden: true });
        commuteMap?.renderRoute(route.geometry, payload.origin, payload.destination);
    };

    const syncModeOptions = () => {
        if (!(modeSelect instanceof HTMLSelectElement) || !Array.isArray(payload?.modes)) {
            return;
        }
        modeSelect.innerHTML = payload.modes
            .map((mode) => `<option value="${mode.value}">${mode.label}</option>`)
            .join("");
        modeSelect.value = payload.default_mode || "walking";
    };

    const loadCommute = async () => {
        setMapNote("Loading route map.");
        try {
            const response = await fetch(config.endpoint_url, {
                headers: {
                    Accept: "application/json",
                },
            });
            if (!response.ok) {
                throw new Error(`Commute request failed with status ${response.status}`);
            }

            payload = await response.json();
            syncModeOptions();
            applyMode(modeSelect?.value || payload.default_mode || "walking");
        } catch {
            setUnavailable("Route-backed commute data is unavailable right now.");
        }
    };

    if (modeSelect instanceof HTMLSelectElement) {
        modeSelect.addEventListener("change", () => {
            applyMode(modeSelect.value);
        });
    }

    loadCommute();
}
