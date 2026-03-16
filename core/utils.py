from django.core.paginator import Paginator


def get_page(queryset, page_number, per_page):
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(page_number)


def preserved_query_suffix(params, *excluded_keys):
    query_params = params.copy()
    for key in excluded_keys:
        query_params.pop(key, None)

    encoded = query_params.urlencode()
    return f"&{encoded}" if encoded else ""
