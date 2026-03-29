const optionButtons = Array.from(document.querySelectorAll('[data-group-option]'));
const listingPanels = Array.from(document.querySelectorAll('[data-group-listings-panel]'));
const comparisonRows = Array.from(document.querySelectorAll('[data-group-row]'));

const setButtonState = (button, isActive) => {
    button.classList.toggle('is-active', isActive);
    button.classList.toggle('is-expanded', isActive);
    button.setAttribute('aria-expanded', isActive ? 'true' : 'false');
};

const hideAllPanels = () => {
    optionButtons.forEach((button) => setButtonState(button, false));
    listingPanels.forEach((panel) => panel.setAttribute('hidden', 'hidden'));
    comparisonRows.forEach((row) => row.classList.remove('is-active'));
};

const showPanel = (selectedId) => {
    hideAllPanels();
    const activeButton = optionButtons.find((button) => button.dataset.groupId === selectedId);
    const activePanel = listingPanels.find((panel) => panel.dataset.groupId === selectedId);
    if (activeButton) {
        setButtonState(activeButton, true);
    }
    if (activePanel) {
        activePanel.removeAttribute('hidden');
    }
    comparisonRows.forEach((row) => {
        row.classList.toggle('is-active', row.dataset.groupId === selectedId);
    });
};

optionButtons.forEach((button) => {
    button.addEventListener('click', (event) => {
        event.stopPropagation();
        const isExpanded = button.classList.contains('is-expanded');
        if (isExpanded) {
            hideAllPanels();
        } else {
            showPanel(button.dataset.groupId);
        }
    });
});

document.addEventListener('click', (event) => {
    if (event.target.closest('[data-group-shell]')) {
        return;
    }
    hideAllPanels();
});
