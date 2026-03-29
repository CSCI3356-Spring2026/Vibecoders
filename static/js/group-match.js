const optionButtons = Array.from(document.querySelectorAll("[data-group-option]"));
const listingPanels = Array.from(document.querySelectorAll("[data-group-listings-panel]"));
const comparisonRows = Array.from(document.querySelectorAll("[data-group-row]"));
const spotlight = document.querySelector("[data-group-spotlight]");

const spotlightFields = spotlight
    ? {
          title: spotlight.querySelector("[data-group-spotlight-title]"),
          headline: spotlight.querySelector("[data-group-spotlight-headline]"),
          summary: spotlight.querySelector("[data-group-spotlight-summary]"),
          fit: spotlight.querySelector("[data-group-spotlight-fit]"),
          listings: spotlight.querySelector("[data-group-spotlight-listings]"),
          price: spotlight.querySelector("[data-group-spotlight-price]"),
          market: spotlight.querySelector("[data-group-spotlight-market]"),
      }
    : null;

const setButtonState = (button, isActive) => {
    button.classList.toggle("is-active", isActive);
    button.classList.toggle("is-expanded", isActive);
    button.setAttribute("aria-expanded", isActive ? "true" : "false");
};

const updateSpotlight = (button) => {
    if (!spotlightFields || !button) {
        return;
    }

    spotlightFields.title.textContent = button.dataset.groupLabel || "";
    spotlightFields.headline.textContent = button.dataset.groupHeadline || "";
    spotlightFields.summary.textContent = button.dataset.groupSummary || spotlight.dataset.emptyText || "";
    spotlightFields.fit.textContent = button.dataset.groupFit || "--";
    spotlightFields.listings.textContent = button.dataset.groupListings || "0";
    spotlightFields.price.textContent = button.dataset.groupPrice || "--";
    spotlightFields.market.textContent = button.dataset.groupMarket || "--";
};

const syncQueryString = (selectedId) => {
    const url = new URL(window.location.href);
    if (selectedId) {
        url.searchParams.set("group", selectedId);
    } else {
        url.searchParams.delete("group");
    }
    window.history.replaceState({}, "", url);
};

const showPanel = (selectedId) => {
    const activeButton = optionButtons.find((button) => button.dataset.groupId === selectedId);

    optionButtons.forEach((button) => setButtonState(button, button === activeButton));
    listingPanels.forEach((panel) => {
        panel.toggleAttribute("hidden", panel.dataset.groupId !== selectedId);
    });
    comparisonRows.forEach((row) => {
        row.classList.toggle("is-active", row.dataset.groupId === selectedId);
    });

    updateSpotlight(activeButton || null);
    syncQueryString(selectedId);
};

optionButtons.forEach((button) => {
    button.addEventListener("click", () => {
        showPanel(button.dataset.groupId);
    });
});

comparisonRows.forEach((row) => {
    row.addEventListener("click", () => {
        showPanel(row.dataset.groupId);
    });
});
