from django.core.paginator import Paginator
from django.utils.http import url_has_allowed_host_and_scheme


def get_page(queryset, page_number, per_page):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page_number)


def preserved_query_suffix(params, *excluded_keys):
    query_params = params.copy()
    for key in excluded_keys:
        query_params.pop(key, None)

    encoded = query_params.urlencode()
    return f"&{encoded}" if encoded else ""


def safe_next_url(request, next_url, fallback_url):
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url
