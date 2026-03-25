const listingMapRoot = document.querySelector("[data-listing-map-root]");
const listingMapPayload = document.getElementById("listing-map-data");

function buildPopupNode(item) {
    const wrapper = document.createElement("div");
    wrapper.className = "listing-map-popup";

    const title = document.createElement("h3");
    title.className = "listing-map-popup-title";
    title.textContent = item.title;
    wrapper.appendChild(title);

    const address = document.createElement("p");
    address.className = "listing-map-popup-address";
    address.textContent = item.address;
    wrapper.appendChild(address);

    const price = document.createElement("p");
    price.className = "listing-map-popup-price";
    price.textContent = `$${item.price}/mo`;
    wrapper.appendChild(price);

    return wrapper;
}

if (listingMapRoot && listingMapPayload && typeof maplibregl !== "undefined") {
    const mapCanvas = listingMapRoot.querySelector("[data-listing-map-canvas]");

    let mapData = [];
    try {
        mapData = JSON.parse(listingMapPayload.textContent || "[]");
    } catch {
        mapData = [];
    }

    if (mapCanvas && mapData.length) {
        const defaultLat = Number(listingMapRoot.dataset.defaultLat || 42.3355);
        const defaultLng = Number(listingMapRoot.dataset.defaultLng || -71.1685);
        const map = new maplibregl.Map({
            container: mapCanvas,
            style: {
                version: 8,
                sources: {
                    openstreetmap: {
                        type: "raster",
                        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
                        tileSize: 256,
                        attribution: "&copy; OpenStreetMap contributors",
                    },
                },
                layers: [
                    {
                        id: "openstreetmap",
                        type: "raster",
                        source: "openstreetmap",
                    },
                ],
            },
            center: [defaultLng, defaultLat],
            zoom: 12,
        });
        const bounds = new maplibregl.LngLatBounds();
        let hasBounds = false;

        map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

        mapData.forEach((item) => {
            const popup = new maplibregl.Popup({ offset: 18 }).setDOMContent(buildPopupNode(item));

            new maplibregl.Marker({ color: "#1f4d67" })
                .setLngLat([item.lng, item.lat])
                .setPopup(popup)
                .addTo(map);

            bounds.extend([item.lng, item.lat]);
            hasBounds = true;
        });

        if (hasBounds && mapData.length > 1) {
            map.fitBounds(bounds, { padding: 56, maxZoom: 14 });
        } else if (hasBounds) {
            map.setCenter([mapData[0].lng, mapData[0].lat]);
            map.setZoom(13);
        }
    }
}
