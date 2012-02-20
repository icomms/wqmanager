from django.db import models
from django.contrib.auth.models import User
from datetime import timedelta, datetime, date

class LogEntry(models.Model):
    user = models.ForeignKey(User, related_name='ui_log_entries')
    timestamp = models.DateTimeField()
    processing_time_ms = models.BigIntegerField()
    post_data = models.TextField()    
    
    EVENT_TYPE = (
        ('login', 'Manager login'),
        ('logout', 'Manager logout'),
        ('rep_full', 'Full report'),
        ('rep_site_test_count', 'Site test count report'),
        ('rep_test_count', 'Reporter test count report'),
        ('rep_reporter_name', 'Reporter test report excel download (from search on name)'),
        ('rep_reporter_tel', 'Reporter test report excel download (from search on tel)'),
        ('rep_prev_reporter_name', 'Reporter test report html preview (from search on name)'),
        ('rep_prev_reporter_tel', 'Reporter test report html preview (from search on tel)'),
        ('page_search', 'Page - Reporter search'),
        ('page_mapview', 'Page - Map view'),
        ('page_admin', 'Page - Admin'),
    )
    
    event_type = models.CharField(max_length=50, choices=EVENT_TYPE)
    
    def set_processing_time(self, start_time):
        self.processing_time_ms = ((float((datetime.now() - start_time).microseconds)) / float(1000.0))	
    
    def __unicode__(self):
        return '%s - %s' % (self.user, self.event_type)
    
    class Meta:
        verbose_name_plural = "Log entries"

# Create your Django models here, if you need them.
