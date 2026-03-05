from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect


# Ensures that only BC email addresses can log in
class BCEmailAdapter(DefaultSocialAccountAdapter):
    # Method called when a user logs in via social account
    def pre_social_login(self, request, sociallogin):
        # Get the email address from the social account
        email = sociallogin.account.extra_data.get("email", "")

        # Check if the email address is a BC email
        if not email.endswith("@bc.edu"):
            messages.error(request, "Only @bc.edu email addresses are allowed.")
            raise ImmediateHttpResponse(redirect("/"))
