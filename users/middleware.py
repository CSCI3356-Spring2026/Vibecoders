from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from core.utils import safe_next_url


class CurrentLegalAcceptanceMiddleware:
    allowed_view_names = {
        "users:login",
        "account_login",
        "account_logout",
        "google_login",
        "core:terms",
        "core:privacy",
    }
    stale_acceptance_message = "Review and accept the latest Terms of Service and Privacy Policy before continuing."

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if not getattr(user, "is_authenticated", False):
            return None
        if not getattr(user, "terms_accepted_at", None) or not getattr(user, "privacy_accepted_at", None):
            return None
        if user.has_current_legal_acceptance:
            return None

        resolver_match = getattr(request, "resolver_match", None)
        if resolver_match and resolver_match.view_name in self.allowed_view_names:
            return None

        logout(request)
        messages.error(request, self.stale_acceptance_message)
        next_url = safe_next_url(request, request.get_full_path(), "")
        login_url = reverse("users:login")
        if not next_url:
            return redirect(login_url)
        return redirect(f"{login_url}?{urlencode({'next': next_url})}")
