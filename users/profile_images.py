from urllib.parse import urlparse

from allauth.socialaccount.models import SocialAccount


def _is_allowed_profile_image_url(url):
    parsed = urlparse(url)
    return parsed.scheme == "https" and bool(parsed.netloc)


def profile_image_url_from_data(data):
    payload = data or {}
    for key in ("picture", "picture_url", "avatar_url", "image_url", "photo"):
        value = (payload.get(key) or "").strip()
        if value and _is_allowed_profile_image_url(value):
            return value
    return ""


def sync_profile_image_for_user(user, *, extra_data=None):
    image_url = profile_image_url_from_data(extra_data)
    if not image_url:
        account = SocialAccount.objects.filter(user=user, provider="google").only("extra_data").first()
        if account is None:
            return False
        image_url = profile_image_url_from_data(account.extra_data)
    if not image_url:
        return False
    if user.profile_image_url == image_url:
        return False

    user.profile_image_url = image_url
    user.save(update_fields=["profile_image_url"])
    return True
