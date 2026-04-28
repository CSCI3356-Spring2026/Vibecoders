function builtInSatelliteStyle() {
    return {
        version: 8,
        sources: {
            satellite: {
                type: "raster",
                tiles: ["https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
                tileSize: 256,
                attribution: "Imagery © Esri",
            },
        },
        layers: [
            {
                id: "satellite",
                type: "raster",
                source: "satellite",
                minzoom: 0,
                maxzoom: 22,
            },
        ],
    };
}

const MARKER_SOURCE_ID = "listings-markers";
const CLUSTER_LAYER_ID = "listings-clusters";
const CLUSTER_COUNT_LAYER_ID = "listings-cluster-count";
const POINT_LAYER_ID = "listings-points";
const LABEL_LAYER_ID = "listings-point-labels";

function markerFeature(markerData, activeListingId) {
    return {
        type: "Feature",
        geometry: {
            type: "Point",
            coordinates: [markerData.lng, markerData.lat],
        },
        properties: {
            id: String(markerData.id),
            price: markerData.price,
            title: markerData.title,
            selected: String(markerData.id) === activeListingId,
        },
    };
}

function markerFeatureCollection(markers, activeListingId) {
    return {
        type: "FeatureCollection",
        features: (Array.isArray(markers) ? markers : []).map((marker) => markerFeature(marker, activeListingId)),
    };
}

export function createListingsMapView({
    root,
    defaultStyleUrl,
    satelliteStyleUrl = "",
    defaultLat,
    defaultLng,
    initialMarkers = [],
    selectedListingId = "",
    onMarkerSelect,
    onViewportChange,
}) {
    const canvas = root?.querySelector("[data-listings-map-canvas]");
    const markerDocument =
        root?.ownerDocument || canvas?.ownerDocument || (typeof document !== "undefined" ? document : null);
    const resolvedDefaultStyleUrl = defaultStyleUrl || root?.dataset.listingsMapDefaultStyleUrl || "";
    const resolvedSatelliteStyleUrl = satelliteStyleUrl || root?.dataset.listingsMapSatelliteStyleUrl || "";

    if (!root || !canvas || !resolvedDefaultStyleUrl || typeof maplibregl === "undefined") {
        return {
            getBounds() {
                return null;
            },
            getStyleMode() {
                return "map";
            },
            setStyleMode() {},
            setSelectedListing() {},
            renderMarkers() {},
        };
    }

    const resolveStyle = (mode) => {
        if (mode === "satellite" && resolvedSatelliteStyleUrl) {
            if (resolvedSatelliteStyleUrl === "builtin://satellite") {
                return builtInSatelliteStyle();
            }
            return resolvedSatelliteStyleUrl;
        }
        return resolvedDefaultStyleUrl;
    };

    let activeStyleMode = "map";
    let mapLoaded = false;
    let hasAppliedInitialViewport = false;
    let markers = Array.isArray(initialMarkers) ? initialMarkers : [];
    let activeListingId = selectedListingId ? String(selectedListingId) : "";
    const htmlMarkers = new Map();
    let htmlMarkerSyncTimeout = null;

    const map = new maplibregl.Map({
        container: canvas,
        style: resolveStyle(activeStyleMode),
        center: [defaultLng, defaultLat],
        zoom: 12,
    });
    const canRenderHtmlMarkers = Boolean(markerDocument) && typeof maplibregl.Marker === "function";

    const sourceData = () => markerFeatureCollection(markers, activeListingId);

    const setHtmlMarkerSelectedState = (markerRecord, selected) => {
        markerRecord.element.classList.toggle("is-selected", selected);
        markerRecord.element.setAttribute("aria-pressed", selected ? "true" : "false");
    };

    const removeHtmlMarker = (markerId) => {
        const markerRecord = htmlMarkers.get(markerId);
        if (!markerRecord) {
            return;
        }
        markerRecord.marker.remove();
        htmlMarkers.delete(markerId);
    };

    const markerIdsForCurrentData = () => new Set(markers.map((marker) => String(marker.id)));

    const pruneHtmlMarkersToCurrentData = (currentMarkerIds = markerIdsForCurrentData()) => {
        Array.from(htmlMarkers.keys()).forEach((markerId) => {
            if (!currentMarkerIds.has(markerId)) {
                removeHtmlMarker(markerId);
            }
        });
    };

    const renderedPointFeatures = () => {
        if (typeof map.queryRenderedFeatures === "function") {
            return map.queryRenderedFeatures(undefined, { layers: [POINT_LAYER_ID] }) || [];
        }
        return sourceData().features.filter((feature) => !Object.hasOwn(feature.properties || {}, "point_count"));
    };

    const createHtmlMarkerRecord = (feature) => {
        const markerId = String(feature.properties?.id || "");
        const price = feature.properties?.price || "";
        const title = feature.properties?.title || "Listing";
        const element = markerDocument.createElement("button");
        element.type = "button";
        element.classList.add("listing-map-marker");
        element.dataset.listingId = markerId;
        element.setAttribute("aria-label", `${title}, ${price} per month`);

        const label = markerDocument.createElement("span");
        label.classList.add("listing-map-marker-label");
        label.textContent = price;
        element.append(label);

        element.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            activeListingId = markerId;
            updateSource();
            syncHtmlMarkers();
            onMarkerSelect?.(markerId);
        });

        const marker = new maplibregl.Marker({
            element,
            anchor: "bottom",
        })
            .setLngLat(feature.geometry.coordinates)
            .addTo(map);

        const markerRecord = { element, label, marker };
        setHtmlMarkerSelectedState(markerRecord, markerId === activeListingId);
        return markerRecord;
    };

    const syncHtmlMarkers = () => {
        if (!canRenderHtmlMarkers || !mapLoaded) {
            return;
        }

        const currentMarkerIds = markerIdsForCurrentData();
        pruneHtmlMarkersToCurrentData(currentMarkerIds);
        const visibleMarkerIds = new Set();
        renderedPointFeatures().forEach((feature) => {
            const markerId = String(feature.properties?.id || "");
            const coordinates = feature.geometry?.coordinates;
            if (
                !markerId ||
                !currentMarkerIds.has(markerId) ||
                !Array.isArray(coordinates) ||
                visibleMarkerIds.has(markerId)
            ) {
                return;
            }

            visibleMarkerIds.add(markerId);
            let markerRecord = htmlMarkers.get(markerId);
            if (!markerRecord) {
                markerRecord = createHtmlMarkerRecord(feature);
                htmlMarkers.set(markerId, markerRecord);
            } else {
                markerRecord.marker.setLngLat(coordinates);
                markerRecord.label.textContent = feature.properties?.price || "";
                markerRecord.element.dataset.listingId = markerId;
                markerRecord.element.setAttribute(
                    "aria-label",
                    `${feature.properties?.title || "Listing"}, ${feature.properties?.price || ""} per month`,
                );
            }
            setHtmlMarkerSelectedState(markerRecord, markerId === activeListingId);
        });

        Array.from(htmlMarkers.keys()).forEach((markerId) => {
            if (!visibleMarkerIds.has(markerId)) {
                removeHtmlMarker(markerId);
            }
        });
    };

    const scheduleHtmlMarkerSync = () => {
        if (!canRenderHtmlMarkers || !mapLoaded) {
            return;
        }

        let hasSynced = false;
        const timerHost = typeof window !== "undefined" ? window : globalThis;
        const syncOnce = () => {
            if (hasSynced) {
                return;
            }
            hasSynced = true;
            if (htmlMarkerSyncTimeout !== null && typeof timerHost.clearTimeout === "function") {
                timerHost.clearTimeout(htmlMarkerSyncTimeout);
                htmlMarkerSyncTimeout = null;
            }
            syncHtmlMarkers();
        };

        if (typeof map.once === "function") {
            map.once("idle", syncOnce);
        }
        if (typeof timerHost.setTimeout === "function") {
            htmlMarkerSyncTimeout = timerHost.setTimeout(syncOnce, 160);
        }
    };

    const ensureLayers = () => {
        if (!map.getSource(MARKER_SOURCE_ID)) {
            map.addSource(MARKER_SOURCE_ID, {
                type: "geojson",
                data: sourceData(),
                cluster: true,
                clusterMaxZoom: 14,
                clusterRadius: 48,
            });
        }

        if (!map.getLayer(CLUSTER_LAYER_ID)) {
            map.addLayer({
                id: CLUSTER_LAYER_ID,
                type: "circle",
                source: MARKER_SOURCE_ID,
                filter: ["has", "point_count"],
                paint: {
                    "circle-color": "#ffffff",
                    "circle-radius": [
                        "step",
                        ["get", "point_count"],
                        19,
                        10,
                        23,
                        25,
                        27,
                    ],
                    "circle-opacity": 0.98,
                    "circle-stroke-width": 2.5,
                    "circle-stroke-color": "#d9392e",
                },
            });
        }

        if (!map.getLayer(CLUSTER_COUNT_LAYER_ID)) {
            map.addLayer({
                id: CLUSTER_COUNT_LAYER_ID,
                type: "symbol",
                source: MARKER_SOURCE_ID,
                filter: ["has", "point_count"],
                layout: {
                    "text-field": ["get", "point_count_abbreviated"],
                    "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
                    "text-size": 12,
                },
                paint: {
                    "text-color": "#19212b",
                },
            });
        }

        if (!map.getLayer(POINT_LAYER_ID)) {
            map.addLayer({
                id: POINT_LAYER_ID,
                type: "circle",
                source: MARKER_SOURCE_ID,
                filter: ["!", ["has", "point_count"]],
                paint: {
                    "circle-color": "#ffffff",
                    "circle-radius": 1,
                    "circle-opacity": 0,
                    "circle-stroke-width": 0,
                    "circle-stroke-opacity": 0,
                },
            });
        }

        if (!map.getLayer(LABEL_LAYER_ID)) {
            map.addLayer({
                id: LABEL_LAYER_ID,
                type: "symbol",
                source: MARKER_SOURCE_ID,
                filter: ["!", ["has", "point_count"]],
                layout: {
                    "text-field": ["get", "price"],
                    "text-font": ["Open Sans Semibold", "Arial Unicode MS Bold"],
                    "text-size": 11,
                },
                paint: {
                    "text-color": "#19212b",
                    "text-opacity": 0,
                },
            });
        }
    };

    const updateSource = ({ syncMarkersAfterRender = false } = {}) => {
        const source = map.getSource(MARKER_SOURCE_ID);
        if (source) {
            source.setData(sourceData());
            if (syncMarkersAfterRender) {
                scheduleHtmlMarkerSync();
            }
        }
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
        markers.forEach((marker) => bounds.extend([marker.lng, marker.lat]));
        map.fitBounds(bounds, { padding: 56, maxZoom: 14 });
    };

    const bindEvents = () => {
        map.on("click", CLUSTER_LAYER_ID, (event) => {
            const clusterFeature = event.features?.[0];
            if (!clusterFeature) {
                return;
            }

            const clusterId = clusterFeature.properties?.cluster_id;
            map.getSource(MARKER_SOURCE_ID)?.getClusterExpansionZoom(clusterId, (error, zoom) => {
                if (error) {
                    return;
                }
                map.easeTo({
                    center: clusterFeature.geometry.coordinates,
                    zoom,
                });
            });
        });

        map.on("click", POINT_LAYER_ID, (event) => {
            const feature = event.features?.[0];
            const listingId = feature?.properties?.id;
            if (!listingId) {
                return;
            }

            activeListingId = String(listingId);
            updateSource();
            syncHtmlMarkers();
            onMarkerSelect?.(listingId);
        });

        map.on("mouseenter", CLUSTER_LAYER_ID, () => {
            map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", CLUSTER_LAYER_ID, () => {
            map.getCanvas().style.cursor = "";
        });
        map.on("mouseenter", POINT_LAYER_ID, () => {
            map.getCanvas().style.cursor = "pointer";
        });
        map.on("mouseleave", POINT_LAYER_ID, () => {
            map.getCanvas().style.cursor = "";
        });
    };

    const handleMapStyleReady = () => {
        mapLoaded = true;
        ensureLayers();
        updateSource();
        applyViewportToMarkers();
        syncHtmlMarkers();
    };

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
        handleMapStyleReady();
        bindEvents();
    });
    map.on("style.load", handleMapStyleReady);
    map.on("moveend", () => {
        syncHtmlMarkers();
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
        getStyleMode() {
            return activeStyleMode;
        },
        renderMarkers(nextMarkers) {
            markers = Array.isArray(nextMarkers) ? nextMarkers : [];
            pruneHtmlMarkersToCurrentData();
            updateSource({ syncMarkersAfterRender: true });
            applyViewportToMarkers();
            syncHtmlMarkers();
        },
        setStyleMode(mode) {
            const nextMode = mode === "satellite" && resolvedSatelliteStyleUrl ? "satellite" : "map";
            if (nextMode === activeStyleMode) {
                return;
            }

            activeStyleMode = nextMode;
            mapLoaded = false;
            map.setStyle(resolveStyle(activeStyleMode));
        },
        setSelectedListing(listingId) {
            activeListingId = listingId ? String(listingId) : "";
            updateSource();
            syncHtmlMarkers();
        },
    };
}
