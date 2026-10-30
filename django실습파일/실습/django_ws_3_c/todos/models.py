from django.db import models


class Todo(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    is_completed = models.BooleanField(default=False)

    def __str__(self):
        return self.title


# Create your models here.
