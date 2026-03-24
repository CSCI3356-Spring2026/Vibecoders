from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect

from .legal import has_current_legal_acceptance
from .profile_images import profile_image_url_from_data, sync_profile_image_for_user


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable regular email/password signup — users must use Google OAuth."""

    suppressed_message_templates = {
        "account/messages/logged_in.txt",
        "account/messages/logged_out.txt",
    }

    def is_open_for_signup(self, request):
        return False

    def add_message(
        self,
        request,
        level,
        message_template=None,
        message_context=None,
        extra_tags="",
        message=None,
    ):
        if message_template in self.suppressed_message_templates:
            return
        return super().add_message(
            request,
            level,
            message_template=message_template,
            message_context=message_context,
            extra_tags=extra_tags,
            message=message,
        )


class MarketplaceSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Allow Google login for both student and listing-only accounts."""

    error_message = "Your Google account must provide a verified email address."
    legal_error_message = "Review and accept the Terms of Service and Privacy Policy before continuing."

    def _reject_invalid_login(self, request):
        messages.error(request, self.error_message)
        raise ImmediateHttpResponse(redirect("users:login"))

    def _reject_missing_legal_acceptance(self, request):
        messages.error(request, self.legal_error_message)
        raise ImmediateHttpResponse(redirect("users:login"))

    @staticmethod
    def _normalize_truthy(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @classmethod
    def _email_from_sociallogin(cls, sociallogin, data=None):
        extra_data = getattr(sociallogin.account, "extra_data", {}) or {}
        email = (data or {}).get("email") or extra_data.get("email", "")
        user_model = get_user_model()
        return user_model.normalize_email_address(email)

    @classmethod
    def _has_verified_email(cls, sociallogin, data=None):
        extra_data = getattr(sociallogin.account, "extra_data", {}) or {}
        for key in ("email_verified", "verified_email"):
            if key in extra_data:
                return cls._normalize_truthy(extra_data[key])

        email = cls._email_from_sociallogin(sociallogin, data=data)
        for email_address in getattr(sociallogin, "email_addresses", []) or []:
            is_matching_email = getattr(email_address, "email", "").strip().lower() == email
            if is_matching_email and getattr(email_address, "verified", False):
                return True
        return False

    def _validate_sociallogin_or_reject(self, request, sociallogin, data=None):
        if not has_current_legal_acceptance(request):
            self._reject_missing_legal_acceptance(request)
        has_email = self._email_from_sociallogin(sociallogin, data=data)
        has_verified_email = self._has_verified_email(sociallogin, data=data)
        if not has_email or not has_verified_email:
            self._reject_invalid_login(request)

    @staticmethod
    def _apply_signup_identity(user, email):
        user_model = get_user_model()
        user.email = email
        is_new_user = getattr(getattr(user, "_state", None), "adding", getattr(user, "pk", None) is None)
        if is_new_user:
            user.username = user_model.username_from_email(email)
            user.role = user_model.default_role_for_email(email)

    @staticmethod
    def _preserve_existing_identity(user, fallback_email):
        user_model = get_user_model()
        preserved_email = user.email or fallback_email
        user.email = user_model.normalize_email_address(preserved_email)
        return user

    def is_open_for_signup(self, request, sociallogin):
        """Allow Google signups as long as the provider supplies a verified email."""
        self._validate_sociallogin_or_reject(request, sociallogin)
        return True

    def populate_user(self, request, sociallogin, data):
        """Derive the initial username and role from the verified Google email."""
        existing_user = sociallogin.user if getattr(sociallogin.user, "pk", None) else None
        preserved_username = getattr(existing_user, "username", "")
        preserved_role = getattr(existing_user, "role", None)
        user = super().populate_user(request, sociallogin, data)
        email = self._email_from_sociallogin(sociallogin, data=data)
        if email:
            self._apply_signup_identity(user, email)
            profile_image_url = profile_image_url_from_data(data) or profile_image_url_from_data(
                getattr(sociallogin.account, "extra_data", {})
            )
            if profile_image_url:
                user.profile_image_url = profile_image_url
            if existing_user:
                user.username = preserved_username
                user.role = preserved_role
                self._preserve_existing_identity(user, email)
        return user

    def pre_social_login(self, request, sociallogin):
        """Reject provider responses without a verified email before login completes."""
        self._validate_sociallogin_or_reject(request, sociallogin)
        if getattr(sociallogin.user, "pk", None):
            sync_profile_image_for_user(sociallogin.user, extra_data=getattr(sociallogin.account, "extra_data", {}))
