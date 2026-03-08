from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect


class NoSignupAccountAdapter(DefaultAccountAdapter):
    """Disable regular email/password signup — users must use Google OAuth."""

    def is_open_for_signup(self, request):
        return False


class BCEmailAdapter(DefaultSocialAccountAdapter):
    """Only allow @bc.edu Google accounts to sign in / sign up."""

    def is_open_for_signup(self, request, sociallogin):
        """Block non-BC emails at social signup time."""
        email = sociallogin.account.extra_data.get("email", "")
        if not email.endswith("@bc.edu"):
            return False
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
        if not email.endswith("@bc.edu"):
            messages.error(request, "Only @bc.edu email addresses are allowed.")
            raise ImmediateHttpResponse(redirect("/"))
