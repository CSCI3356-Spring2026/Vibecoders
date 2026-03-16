document.addEventListener("click", (event) => {
    const toggle = event.target.closest("[data-delete-toggle]");
    if (toggle) {
        const confirmId = toggle.dataset.deleteToggle;
        const confirmForm = document.querySelector(`[data-delete-confirm="${confirmId}"]`);
        if (confirmForm) {
            confirmForm.classList.remove("d-none");
            toggle.classList.add("d-none");
        }
        return;
    }

    const cancel = event.target.closest("[data-delete-cancel]");
    if (cancel) {
        const confirmForm = cancel.closest("[data-delete-confirm]");
        if (!confirmForm) {
            return;
        }
        confirmForm.classList.add("d-none");
        const confirmId = confirmForm.dataset.deleteConfirm;
        if (!confirmId) {
            return;
        }
        const toggleButton = document.querySelector(`[data-delete-toggle="${confirmId}"]`);
        if (toggleButton) {
            toggleButton.classList.remove("d-none");
        }
    }
});
