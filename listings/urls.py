from django.urls import path

from . import views

app_name = "listings"

# temporary to test base.html
urlpatterns = [path("", views.home, name="home")]
