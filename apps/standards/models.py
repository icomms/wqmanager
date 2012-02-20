from django.db import models
from datetime import datetime

class WaterUseType(models.Model):
    description = models.CharField(max_length=100)
    modified = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()            
        super(WaterUseType, self).save(*args, **kwargs)
        
    def __unicode__(self):
        return self.description

class Standard(models.Model):
    name = models.CharField(max_length=100)
    governing_body = models.CharField(max_length=100)
    date_effective = models.DateField()
    modified = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()            
        super(Standard, self).save(*args, **kwargs)
        
    def __unicode__(self):
        return self.name
