from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import redirect


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

    error_message = "Your Google account must provide an email address."

    def _reject_invalid_login(self, request):
        messages.error(request, self.error_message)
        raise ImmediateHttpResponse(redirect("users:login"))

    @staticmethod
    def _email_from_sociallogin(sociallogin):
        return sociallogin.account.extra_data.get("email", "").strip().lower()

    def is_open_for_signup(self, request, sociallogin):
        """Allow Google signups as long as the provider supplies an email."""
        if not self._email_from_sociallogin(sociallogin):
            self._reject_invalid_login(request)
        return True

    def populate_user(self, request, sociallogin, data):
        """Derive the username and default role from the Google email."""
        user = super().populate_user(request, sociallogin, data)
        email = (data.get("email") or "").strip().lower()
        if email:
            user_model = get_user_model()
            user.username = user_model.username_from_email(email)
            user.role = user_model.default_role_for_email(email)
        return user

    def pre_social_login(self, request, sociallogin):
        """Reject provider responses without an email before login completes."""
        if not self._email_from_sociallogin(sociallogin):
            self._reject_invalid_login(request)
