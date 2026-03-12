# Create your models here.
from django.db import models
from django.conf import settings

class Listing(models.Model):
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='listings'
    )


    title = models.CharField(max_length=200)
    address = models.CharField(max_length=255, help_text="Street address or Area")
    price = models.DecimalField(max_digits=10, decimal_places=2)

    start_date = models.DateField()
    end_date = models.DateField()
    description = models.TextField(blank=True, help_text="Minimal description of the dorm")


    LEASE_TYPES = [
        ('SUBLEASE', 'Sublease'),
        ('FULL', 'Full Lease'),
        ('SHORT', 'Short-term'),
    ]
    lease_type = models.CharField(max_length=20, choices=LEASE_TYPES, default='FULL')

    STATUS_CHOICES = [
        ('AVAILABLE', 'Available'),
        ('PENDING', 'Pending'),
        ('TAKEN', 'Taken'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='AVAILABLE')
    

    is_hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} - ${self.price}"