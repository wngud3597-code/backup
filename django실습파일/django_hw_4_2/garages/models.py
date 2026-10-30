from django.db import models


class Garage(models.Model):
    location = models.CharField(max_length=200)
    capacity = models.IntegerField()
    is_parking_available = models.BooleanField()
    opening_time = models.TimeField()
    closing_time = models.TimeField()
