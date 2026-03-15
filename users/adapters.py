from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
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


class BCEmailAdapter(DefaultSocialAccountAdapter):
    """Only allow @bc.edu Google accounts to sign in / sign up."""

    error_message = "Use your @bc.edu Google account to continue."

    def _reject_non_bc_login(self, request):
        messages.error(request, self.error_message)
        raise ImmediateHttpResponse(redirect("users:login"))

    @staticmethod
    def _is_bc_email(email):
        return email.lower().endswith("@bc.edu")

    def is_open_for_signup(self, request, sociallogin):
        """Block non-BC emails at social signup time."""
        email = sociallogin.account.extra_data.get("email", "")
        if not self._is_bc_email(email):
            self._reject_non_bc_login(request)
        return True

    def populate_user(self, request, sociallogin, data):
        """Set username from the Google email prefix (e.g. 'eagle' from 'eagle@bc.edu')."""
        user = super().populate_user(request, sociallogin, data)
        email = data.get("email", "")
        if email:
            user.username = email.split("@")[0]
        return user

    def pre_social_login(self, request, sociallogin):
        """Block non-BC emails at social login time (returning users)."""
        email = sociallogin.account.extra_data.get("email", "")
        if not self._is_bc_email(email):
            self._reject_non_bc_login(request)
