from django.db import models

class Device(models.Model):   
    device = models.CharField(max_length=30)
    last_update = models.DateTimeField(blank=True, null=True)

    def __unicode__(self):
        return self.device