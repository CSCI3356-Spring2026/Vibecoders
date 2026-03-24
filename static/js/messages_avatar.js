export function initialFromName(name) {
    const trimmed = (name || "").trim();
    return trimmed ? trimmed.charAt(0).toUpperCase() : "?";
}

export function buildUserAvatar({ name, imageUrl, sizeClass, extraClass = "" }) {
    const avatar = document.createElement("span");
    avatar.className = ["user-avatar", sizeClass, extraClass].filter(Boolean).join(" ");

    if (imageUrl) {
        const image = document.createElement("img");
        image.className = "user-avatar-image";
        image.src = imageUrl;
        image.alt = name || "User avatar";
        avatar.appendChild(image);
        return avatar;
    }

    const fallback = document.createElement("span");
    fallback.className = "user-avatar-fallback";
    fallback.setAttribute("aria-hidden", "true");
    fallback.textContent = initialFromName(name);
    avatar.appendChild(fallback);
    return avatar;
}
