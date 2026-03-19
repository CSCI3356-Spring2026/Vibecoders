from django.conf import settings


def branding(request):
    return {
        "site_product_name": getattr(settings, "SITE_PRODUCT_NAME", "Padly"),
        "site_company_name": getattr(settings, "SITE_COMPANY_NAME", "Vibecoders"),
        "site_legal_version": getattr(settings, "LEGAL_DOCUMENT_VERSION", ""),
    }
