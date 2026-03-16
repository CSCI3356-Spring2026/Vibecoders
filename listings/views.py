from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ListingForm
from .models import Listing, ListingImage


def listing_detail(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    data = {
        "title": listing.title,
        "address": listing.address,
        "price": str(listing.price),
        "description": listing.description,
        "rooms": listing.rooms,
        "bathrooms": str(listing.bathrooms),
        "sq_ft": listing.sq_ft,
        "lease_type": listing.get_lease_type_display(),
        "property_type": listing.get_property_type_display(),
        "status": listing.get_status_display(),
        "start_date": str(listing.start_date),
        "end_date": str(listing.end_date),
        "has_yard": listing.has_yard,
        "has_parking": listing.has_parking,
        "is_furnished": listing.is_furnished,
        "utilities_included": listing.utilities_included,
        "pet_policy": listing.pet_policy,
        "amenities": listing.amenities,
        "owner": listing.owner.get_full_name() or listing.owner.email,
        "images": [request.build_absolute_uri(img.image.url) for img in listing.images.all()],
    }
    return JsonResponse(data)


def listing_list(request):
    listings = Listing.objects.filter(is_hidden=False).order_by("-created_at")

    return render(request, "listings/listing_list.html", {"listings": listings})


@login_required
def create_listing(request):
    if request.method == "POST":
        form = ListingForm(request.POST, request.FILES)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()
            for image in request.FILES.getlist("images"):
                ListingImage.objects.create(listing=listing, image=image)
            return redirect("listings:listing_list")
    else:
        form = ListingForm()

    return render(request, "listings/listing_form.html", {"form": form})
