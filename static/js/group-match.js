(() => {
    const onReady = (fn) => {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn, { once: true });
        } else {
            fn();
        }
    };

    onReady(() => {
    const setupOpenSpotsToggle = (form, fieldSelector) => {
        if (!form) {
            return;
        }
        const housingSelect = form.querySelector("[name='housing_status']");
        const openSpotsField = form.querySelector(fieldSelector);
        if (!housingSelect || !openSpotsField) {
            return;
        }
        const openSpotsInput = openSpotsField.querySelector("input, select, textarea");

        const toggleOpenSpots = () => {
            const shouldShow = housingSelect.value === "have_home";
            if (shouldShow) {
                openSpotsField.removeAttribute("hidden");
                openSpotsField.style.display = "";
            } else {
                openSpotsField.setAttribute("hidden", "");
                openSpotsField.style.display = "none";
            }
            if (openSpotsInput) {
                openSpotsInput.disabled = !shouldShow;
            }
        };

        toggleOpenSpots();
        housingSelect.addEventListener("change", toggleOpenSpots);
        housingSelect.addEventListener("input", toggleOpenSpots);
    };

    setupOpenSpotsToggle(document.querySelector(".group-board-filter-form"), ".js-open-spots-filter");
    setupOpenSpotsToggle(document.querySelector(".group-board-post-form"), ".js-open-spots-post");
    });
})();
