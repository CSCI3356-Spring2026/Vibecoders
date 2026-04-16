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

    document.querySelectorAll(".group-board-filter-form").forEach((form) => {
        setupOpenSpotsToggle(form, ".js-open-spots-filter");
    });
    document.querySelectorAll(".group-board-post-form").forEach((form) => {
        setupOpenSpotsToggle(form, ".js-open-spots-post");
    });
    });
})();
