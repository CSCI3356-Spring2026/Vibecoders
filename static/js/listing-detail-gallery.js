function updateGallery(gallery, nextIndex) {
    const image = gallery.querySelector("[data-listing-gallery-active-image]");
    const count = gallery.querySelector("[data-listing-gallery-count]");
    const thumbs = Array.from(gallery.querySelectorAll("[data-listing-gallery-thumb]"));

    if (!(image instanceof HTMLImageElement) || thumbs.length === 0) {
        return;
    }

    const boundedIndex = ((nextIndex % thumbs.length) + thumbs.length) % thumbs.length;
    const activeThumb = thumbs[boundedIndex];
    const imageUrl = activeThumb.dataset.imageUrl || "";
    const imageAlt = activeThumb.dataset.imageAlt || image.alt;

    image.src = imageUrl;
    image.alt = imageAlt;

    thumbs.forEach((thumb, index) => {
        const isActive = index === boundedIndex;
        thumb.classList.toggle("is-active", isActive);
        thumb.setAttribute("aria-current", isActive ? "true" : "false");
    });

    if (count instanceof HTMLElement) {
        count.textContent = `${boundedIndex + 1} / ${thumbs.length}`;
    }

    gallery.dataset.activeIndex = String(boundedIndex);
}

document.addEventListener("DOMContentLoaded", () => {
    const gallery = document.querySelector("[data-listing-gallery]");
    if (!(gallery instanceof HTMLElement)) {
        return;
    }

    const thumbs = Array.from(gallery.querySelectorAll("[data-listing-gallery-thumb]"));
    if (thumbs.length < 2) {
        return;
    }

    gallery.addEventListener("click", (event) => {
        const thumb = event.target.closest("[data-listing-gallery-thumb]");
        if (thumb instanceof HTMLElement && gallery.contains(thumb)) {
            event.preventDefault();
            updateGallery(gallery, Number(thumb.dataset.imageIndex || 0));
            return;
        }

        const prevButton = event.target.closest("[data-listing-gallery-prev]");
        if (prevButton instanceof HTMLElement) {
            event.preventDefault();
            updateGallery(gallery, Number(gallery.dataset.activeIndex || 0) - 1);
            return;
        }

        const nextButton = event.target.closest("[data-listing-gallery-next]");
        if (nextButton instanceof HTMLElement) {
            event.preventDefault();
            updateGallery(gallery, Number(gallery.dataset.activeIndex || 0) + 1);
        }
    });

    updateGallery(gallery, Number(gallery.dataset.activeIndex || 0));
});
