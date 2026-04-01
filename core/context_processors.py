from django.conf import settings

from communications.selectors import conversation_summary_for_user


def branding(request):
    context = {
        "site_product_name": getattr(settings, "SITE_PRODUCT_NAME", "Padly"),
        "site_company_name": getattr(settings, "SITE_COMPANY_NAME", "Vibecoders"),
        "site_legal_version": getattr(settings, "LEGAL_DOCUMENT_VERSION", ""),
    }

    user = getattr(request, "user", None)
    if getattr(user, "is_authenticated", False):
        context["global_unread_conversations_count"] = conversation_summary_for_user(user)["unread_conversations_count"]
    else:
        context["global_unread_conversations_count"] = 0

    return context
