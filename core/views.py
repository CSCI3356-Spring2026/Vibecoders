from django.contrib.auth.decorators import login_required
from django.shortcuts import render


# Basic landing page view
def landing(request):
    return render(request, "core/landing.html")


@login_required
def welcome(request):
    return render(request, "core/welcome.html")
