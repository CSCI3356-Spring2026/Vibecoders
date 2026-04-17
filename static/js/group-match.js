(() => {
    const onReady = (fn) => {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", fn, { once: true });
        } else {
            fn();
        }
    };

    onReady(() => {
    const setupHousingDependentToggle = (form, fieldSelector, shouldShow) => {
        if (!form) {
            return;
        }
        const housingSelect = form.querySelector("[name='housing_status']");
        const openSpotsField = form.querySelector(fieldSelector);
        if (!housingSelect || !openSpotsField) {
            return;
        }
        const openSpotsInput = openSpotsField.querySelector("input, select, textarea");

        const toggleField = () => {
            const show = shouldShow(housingSelect.value);
            if (show) {
                openSpotsField.removeAttribute("hidden");
                openSpotsField.style.display = "";
            } else {
                openSpotsField.setAttribute("hidden", "");
                openSpotsField.style.display = "none";
            }
            if (openSpotsInput) {
                openSpotsInput.disabled = !show;
            }
        };

        toggleField();
        housingSelect.addEventListener("change", toggleField);
        housingSelect.addEventListener("input", toggleField);
    };

    document.querySelectorAll(".group-board-filter-form").forEach((form) => {
        setupHousingDependentToggle(form, ".js-open-spots-filter", (value) => value === "have_home");
    });
    document.querySelectorAll(".group-board-post-form").forEach((form) => {
        setupHousingDependentToggle(form, ".js-open-spots-post", (value) => value === "have_home");
    });

    // Toggle linked listing expansion when clicking the post title button
    document.querySelectorAll(".js-toggle-linked-listing").forEach((button) => {
        const targetId = button.getAttribute("data-target");
        if (!targetId) return;
        const target = document.querySelector(targetId);
        if (!target) return;
        button.addEventListener("click", () => {
            const isHidden = target.hasAttribute("hidden");
            target.toggleAttribute("hidden", !isHidden);
            button.setAttribute("aria-expanded", isHidden ? "true" : "false");
        });
    });
    });
})();
