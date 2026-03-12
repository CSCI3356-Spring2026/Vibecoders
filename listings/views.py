from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Listing
from .forms import ListingForm

# Minimal current views for listing-related pages
def search(request):
    return render(request, "listings/search.html")


def listing_detail(request):
    return render(request, "listings/listing_detail.html")


def create_listing(request):
    return render(request, "listings/create_listing.html")

def listing_list(request):
    listings = Listing.objects.filter(is_hidden=False).order_by('-created_at')
    
    return render(request, 'listings/listing_list.html', {'listings': listings})

@login_required
def create_listing(request):
    if request.method == 'POST':
        form = ListingForm(request.POST)
        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user 
            listing.save()
            return redirect('listing_list') # Send them back to the feed
    else:
        form = ListingForm()
    
    return render(request, 'listings/listing_form.html', {'form': form})