from datetime import datetime

from django.db import models

from xformmanager.models import FormDefModel
from wqm.models import WqmAuthority, SamplingPoint
    
class Manager(models.Model):
    wqmauthority = models.ForeignKey(WqmAuthority)
    
    name = models.CharField(max_length=200)
    email = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=60, help_text="Including international dialing code", blank=True)
    is_active = models.NullBooleanField(null=True, blank=True)    
    
    def __unicode__(self):
        return self.name

class OkMessage(models.Model):
    wqmauthority = models.ForeignKey(WqmAuthority)   
    message_text = models.CharField(max_length=255, help_text="Can use %date%, %sitename%, %sitecode% and %operatorname% as place-holders")
    
    def __unicode__(self):
        return self.wqmauthority.code 

class SmsNotification(models.Model):
    #failure_notification = models.BooleanField(default=False, help_text="select if you want to send sms only when value is out of range")    
    xform = models.ForeignKey(FormDefModel, blank=True, null=True)
    wqmauthority = models.ForeignKey(WqmAuthority)    
    message_text = models.CharField(max_length=255, help_text="Can use %date%, %sitename%, %sitecode% and %operatorname% as place-holders")
    send_to_operator = models.BooleanField(default=False, help_text="You probably don't want to choose any managers if this is selected")
    manager = models.ManyToManyField(Manager, blank=True)        
    normalrange = models.ManyToManyField('samples.NormalRange') # fully qualified to stop circular importing
    description = models.CharField(max_length=50, help_text="Short description of notification")
    modified = models.DateTimeField(null=True, blank=True)
    created = models.DateTimeField(default=datetime.utcnow)
    samplingpoint = models.ManyToManyField(SamplingPoint, blank=True)
    send_message_per_error = models.BooleanField(default=False)
    is_active = models.NullBooleanField(null=True, blank=True)    
        
    def __unicode__(self):
        return '%s notification for %s' % (self.description, self.wqmauthority)
    