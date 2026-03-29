const optionButtons = Array.from(document.querySelectorAll('[data-group-option]'));
const listingPanels = Array.from(document.querySelectorAll('[data-group-listings-panel]'));
const comparisonRows = Array.from(document.querySelectorAll('[data-group-row]'));

const hideAllPanels = () => {
    optionButtons.forEach((button) => button.classList.remove('is-active', 'is-expanded'));
    listingPanels.forEach((panel) => panel.setAttribute('hidden', 'hidden'));
    comparisonRows.forEach((row) => row.classList.remove('is-active'));
};

const showPanel = (selectedId) => {
    hideAllPanels();
    const activeButton = optionButtons.find((button) => button.dataset.groupId === selectedId);
    const activePanel = listingPanels.find((panel) => panel.dataset.groupId === selectedId);
    if (activeButton) {
        activeButton.classList.add('is-active', 'is-expanded');
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
