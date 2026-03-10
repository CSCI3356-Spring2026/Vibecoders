from django.shortcuts import render


# Minimal current views for listing-related pages
def search(request):
    return render(request, "listings/search.html")


def listing_detail(request):
    return render(request, "listings/listing_detail.html")


def create_listing(request):
    return render(request, "listings/create_listing.html")
