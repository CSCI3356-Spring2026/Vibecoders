from django.conf import settings
from django.core.cache import cache

from communications.cache import global_unread_conversations_count_cache_key
from communications.selectors import conversation_summary_for_user


def global_unread_conversations_count_for_user(user):
    cache_timeout = getattr(settings, "GLOBAL_UNREAD_COUNT_CACHE_SECONDS", 30)
    if cache_timeout <= 0:
        return conversation_summary_for_user(user)["unread_conversations_count"]

    cache_key = global_unread_conversations_count_cache_key(user.pk)
    cached_count = cache.get(cache_key)
    if cached_count is not None:
        return cached_count

    unread_count = conversation_summary_for_user(user)["unread_conversations_count"]
    cache.set(cache_key, unread_count, cache_timeout)
    return unread_count


def branding(request):
    context = {
        "site_product_name": getattr(settings, "SITE_PRODUCT_NAME", "Padly"),
        "site_company_name": getattr(settings, "SITE_COMPANY_NAME", "Vibecoders"),
        "site_legal_version": getattr(settings, "LEGAL_DOCUMENT_VERSION", ""),
    }

    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        context["global_unread_conversations_count"] = global_unread_conversations_count_for_user(user)
    else:
        context["global_unread_conversations_count"] = 0

    return context
