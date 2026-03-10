from django.shortcuts import render


# Basic landing page view
def landing(request):
    return render(request, "core/landing.html")
