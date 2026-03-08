# Create your views here.
from django.shortcuts import render


# temporary to test base.html
def home(response):
    return render(response, "base.html", {})
