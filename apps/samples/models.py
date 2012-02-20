import logging
import httplib, urllib, uuid

from threading import Thread
from datetime import datetime, date
from dateutil import parser

from django.db import models
from django.db.models.signals import post_save
from django.contrib.gis.geos import Point

from wqm.models import WqmAuthority, WqmArea, SamplingPoint
from domain.models import Domain
from locations.models import Location, LocationType
from standards.models import Standard, WaterUseType
from reporters.models import Reporter, ReporterGroup, PersistantBackend, PersistantConnection
from xformmanager.models import Metadata, FormDefModel
from hq.models import ReporterProfile
from smsnotifications.models import SmsNotification
from smsnotifications.utils import send_sms_notifications

import urllib2

try:
    import json
except ImportError:
    import simplejson as json

# use the following to restrict which forms can be submitted (see line 390 in this file)
# TODO don't hardcode - check database for registered forms
FORM_XMLNS_1 = "http://www.example.com/ns1"
FORM_XMLNS_2 = "http://www.example.com/ns2"

WQR_XMLNS = [FORM_XMLNS_1, FORM_XMLNS_2]


class SampleDates(models.Model):
    """
        This module adds, modified and created dates for samples modules
    """
    modified = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()
            
        super(SampleDates, self).save(*args, **kwargs)

class Parameter(SampleDates):
    test_name = models.CharField(max_length=120)
    unit = models.CharField(max_length=50, null=True, blank=True)
    lookup_hint = models.BooleanField()
    test_name_short = models.CharField(max_length=20, help_text="must correspond to xform test")
    meta = models.BooleanField(default=False)
    is_decimal = models.NullBooleanField(null=True, blank=True)
    hide_in_summary = models.NullBooleanField(null=True, blank=True)

    def __unicode__(self):
        return self.test_name
    
class ParameterTranslation(models.Model):
    test_name = models.CharField(max_length=120)
    parameter = models.ForeignKey(Parameter)
    wqmauthority = models.ForeignKey(WqmAuthority)
    
    def __unicode__(self):
        return self.test_name

class Sample(SampleDates):
    '''
    This is sample
    '''
    xform = models.ForeignKey(FormDefModel, blank=True, null=True)
    taken_by = models.ForeignKey(Reporter)
    reporter_name = models.CharField(max_length=100, blank=True, null=True)
    sampling_point = models.ForeignKey(SamplingPoint)
    notes = models.CharField(max_length=250, null=True, blank=True)
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    incubated = models.BooleanField(default=False)
    date_taken = models.DateTimeField()
    date_received = models.DateTimeField()    
    meta_uid = models.CharField(max_length=32, null=True)
    date_raw = models.CharField(max_length=50, default="")
    assessment_fields = models.TextField(default="")
    
    class Meta:
        ordering = ['-date_received']

    def __unicode__(self):
        return self.date_received.isoformat()

class MeasuredValue(models.Model):
    parameter = models.ForeignKey(Parameter)
    sample = models.ForeignKey(Sample)
    value = models.CharField(max_length=50, help_text='the value measured')
    modified = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=datetime.utcnow)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()
        
        super(MeasuredValue, self).save(*args, **kwargs)    

    def __unicode__(self):
        return '%s' % (self.value)
    
    def is_range_value(self):
        SEPERATOR = ';'
        return SEPERATOR in self.value
    
    def get_range_parts(self):
        if not self.is_range_value():
            return None
        
        SEPERATOR = ';'
        values = []        

        for word in self.value.replace(SEPERATOR,' ').replace(',',' ').split():
            if (word == '(n/a)'):
                values.append('')
            else:
                try:
                    values.append(float(word))
                except ValueError:
                    pass
                
        parts = {}
        parts['min'] = values[0]
        parts['max'] = values[1]
        parts['avg'] = values[2]
        parts['count'] = values[3]
        
        return parts

    def get_avg_or_value(self):
        parts = self.get_range_parts()
        if parts == None:
            if self.parameter.id == 5:
                if self.value == '0':
                    return 'pass'
                elif self.value == '1':
                    return 'fail'
                else:
                    return self.value
            else:
                return self.value
        
        return parts['avg']

class ValueRule(SampleDates):
    '''
    Rules Applied to the values
    '''
    description = models.TextField()
    parameter = models.ForeignKey(Parameter)
    standard = models.ForeignKey(Standard, null=True, blank=True)
    water_use_type = models.ForeignKey(WaterUseType, null=True, blank=True)

    def __unicode__(self):
        return self.description

class Range(models.Model):
    """
     This class provide the range of the measured values, and the date
     created or modified.
    """
    maximum = models.DecimalField(decimal_places=2, max_digits=7)
    minimum = models.DecimalField(decimal_places=2, max_digits=7)
    modified = models.DateTimeField(blank=True, null=True)
    created = models.DateTimeField(default=datetime.utcnow)
    
    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()
        
        super(Range, self).save(*args, **kwargs)    
    
class NormalRange(Range):
    '''
    Normal range for values.
    '''
    description = models.CharField(max_length=200)
    value_rule = models.ForeignKey(ValueRule)
    wqmauthority = models.ForeignKey(WqmAuthority)

    def __unicode__(self):
        return self.description + " (" + self.wqmauthority.code + ")"

class AbnormalRange(Range):
    description = models.CharField(max_length=255)
    value_rule = models.ForeignKey(ValueRule)
    remedialaction = models.CharField(max_length=20, blank=True)
    color = models.CharField(max_length=25)
    wqmauthority = models.ForeignKey(WqmAuthority)

    def __unicode__(self):
        return self.description + " (" + self.wqmauthority.code + ")"
    
# xform submission methods below    
    
def check_and_add_reporter(data, domain):
    """
    Checks if xform submitter is registered in application, adds details if not    
    Returns new/matching Reporter object
    """        
        
    chw_username = False # chw_username is the mobile phone number (we don't use traditional users in WQR)
    tester_phone_number = False
    tester_name = False
    
    if data.has_key("meta_username"):
        chw_username = str(data["meta_username"])
    
    # trawl xform data for reporter fields
    match_phone = "phonenumber" # TODO remove eventually, when all forms in the wild have meta_username populated
    match_name = "enteredby"
    
    for key in data.keys():
        if key.find(match_phone) != -1:
            tester_phone_number = str(data[key])
            
        if key.find(match_name) != -1:
            tester_name = data[key]
            
    if tester_phone_number == "None":
        tester_phone_number = None
            
    if tester_phone_number and tester_phone_number[0] != '0':
        tester_phone_number = '0' + tester_phone_number
            
    if (not chw_username) or (chw_username is None) or (chw_username == "None"):
        if tester_phone_number:
            chw_username = tester_phone_number
        else:
            # TODO do we really want to bail if there is no number? could assign a fake number
            return None
            
    # check if reporter exists already    
    rps = ReporterProfile.objects.filter(chw_username=chw_username)     
    
    # check if chw_username is missing a leading 0
    if rps.count() == 0 and chw_username[0] != '0':    
        chw_username = '0' + chw_username
        rps = ReporterProfile.objects.filter(chw_username=chw_username)
    
    if rps.count() > 0:
        rp = rps[0]
        persistant_connection = PersistantConnection.objects.get(reporter=rp.reporter)
        persistant_connection.last_seen = datetime.today()
        persistant_connection.save()
        
        return rp.reporter
    else:
        # add reporter
        reporter = Reporter()
        reporter.alias = tester_name
        reporter.first_name = tester_name.split(" ")[0] # first token after splitting on spaces
        reporter.last_name = " ".join(tester_name.split(" ")[1:]) # all other tokens joined by spaces (even if none)
        reporter.registered_self = 1
        reporter.save()
        reporter.groups.add(ReporterGroup.objects.get(title="Operator"))        
        
        # connection 
        persistant_connection = PersistantConnection()
        persistant_connection.backend = PersistantBackend.objects.get(slug="cellphone")
        persistant_connection.reporter = reporter
        persistant_connection.identity = chw_username
        persistant_connection.preferred = True
        persistant_connection.last_seen = datetime.today()
        persistant_connection.save()
        
        # and finally, reporterprofile
        rp = ReporterProfile()
        rp.reporter = reporter
        rp.chw_username = chw_username
            
        rp.domain = domain
        rp.approved = True
        rp.active = True
        rp.guid = str(uuid.uuid1()).replace('-', '')  
        rp.save()
        
        return reporter

def update_reporter_location(reporter, sampling_point):
    reporter.location = sampling_point
    reporter.save()
            
def check_and_add_samplingpoint(data, domain):
    """
    Checks if sampling point exists, adds if not    
    Returns new/matching SamplingPoint object    
    """        
    
    # trawl xform data for point fields
    match_code = "pointcode"
    match_name = "pointname"
    match_area = "areaname"
    
    point_code = False
    point_name = False
    area_name = False
    
    for key in data.keys():
        if key.find(match_code) != -1:
            point_code = data[key]
            
        if key.find(match_name) != -1:
            point_name = data[key]
            
        if key.find(match_area) != -1:
            area_name = data[key]
            
    if not point_name and not area_name:
        return None
    
    if point_code == "None" or point_code == "NEW":
        point_code = None
                            
    if point_code is None:
        points = SamplingPoint.objects.filter(name__iexact=point_name, wqmarea__name__icontains=area_name, active=True)
    else:
        points = SamplingPoint.objects.filter(code__iexact=point_code, name__iexact=point_name, wqmarea__name__icontains=area_name, active=True)
            
    if points.count() > 0:
        return points[0]
    else:
        wqmauthority = WqmAuthority.objects.get(domain=domain)
        
        try:
            wqmarea = WqmArea.objects.get(name__icontains=area_name, wqmauthority=wqmauthority)
        except:
            # fail
            logging.debug("no sample point: " + point_name + ", " + area_name + ", " + wqmauthority.name)
            return None
        
        point = SamplingPoint()
        point.wqmarea = wqmarea
        point.name = point_name
        
        if point_code is not None:
            point.code = point_code
        else:
            point_code = point.generate_site_code()
            
        point.type = LocationType.objects.get(name="point")
        point.active = True
        point.point = Point(0.0, 0.0)
        point.save()
        
        logging.debug("adding sample point: " + point_name)
        
        return point
            
def check_and_add_sample(sender, instance, created, **kwargs):
    try:
        sample_data = instance.formdefmodel.row_as_dict(instance.raw_data)
    except:
        logging.debug("no data")
        return
    
    reporter = check_and_add_reporter(sample_data, instance.formdefmodel.domain)    
    
    if reporter is None:
        logging.debug("no reporter")
        return
    
    sampling_point = check_and_add_samplingpoint(sample_data, instance.formdefmodel.domain)
    
    if sampling_point is None:
        logging.debug("no sample point")
        return
         
    # only process newly created forms, not all of them
    if not created:
        logging.debug("no created")
        return    

    # update reporter location (latest seen location)
    update_reporter_location(reporter, sampling_point)

    form_xmlns = instance.formdefmodel.target_namespace
    prefix = form_xmlns.split("/")[-1] + '_test_'

    assessment_date = None
    
    if True or form_xmlns in WQR_XMLNS:
        sample = Sample()
        sample.created = datetime.utcnow()        
        sample.date_received = instance.attachment.submission.submit_time
        sample.date_taken = datetime.utcnow().strftime("%Y-%m-%d") # default date for now (string)
        sample.taken_by = reporter    
        sample.xform = instance.formdefmodel
        sample.sampling_point = sampling_point
        sample.meta_uid = instance.uid
        
        assessment_fields = {}

        # extract some key fields
        for key in sample_data.keys():
            # hack to find correct column prefix
            if key.find("meta_chw_id") != -1:
                prefix = key.replace('meta_chw_id', '')
            
            if key.find("datacapture_enteredby") != -1:
                sample.reporter_name = sample_data[key]

            if key.find("datacapture_comments") != -1:
                sample.notes = sample_data[key]
                
            if key.find("assessment_assessmentdate") != -1:                
                assessment_date = sample_data[key]
                
            if key.find("assessment_h2sbatch") != -1: # should change forms to be test agnostic
                sample.batch_number = sample_data[key]
            elif key.find("assessment_aquatestcode") != -1:
                sample.batch_number = sample_data[key]
       
        # collect all assessment values (looping again because prefix might not have been correct till now)
        for key in sample_data.keys():            
            if key.find("assessment") != -1:                
                short_key = key.replace(prefix + 'assessment_', '')
                
                if short_key not in ['pointcode', 'assessmentdate', 'pointname', 'areaname']:
                    if sample_data[key] is not None:
                        assessment_fields[short_key] = unicode(sample_data[key])
                    else:  
                        assessment_fields[short_key] = ''
     
        sample.assessment_fields = json.dumps(assessment_fields)               
        sample.date_raw = str(assessment_date)
        skip_date_check = False

        if type(assessment_date) == datetime:
            sample.date_taken = assessment_date.date()
        elif type(assessment_date) == date:
            sample.date_taken = assessment_date
        else:
            try:                
                sample.date_taken = parser.parse(assessment_date, dayfirst=True).date()
                skip_date_check = True
            except ValueError:
                sample.date_taken = sample.date_received.date()
                
        if not skip_date_check:
            # check if date_taken is sane
            diff = (sample.date_received.date() - sample.date_taken).days
        
            # in the future or too old
            if diff < 0 or diff > 30:
                sample.date_taken = sample.date_received.strftime("%Y-%m-%d 00:00:00")
        
        sample.save()
                    
        parameters = Parameter.objects.filter(meta=False)
        
        # hmm        
        tests = {}

        for p in parameters:
            test = prefix + "testresults_" + p.test_name_short
            
            if not sample_data.has_key(test): # physchem hack
                test = prefix + "assessment_" + p.test_name_short
                       
            if sample_data.has_key(test):
                tests[int(p.pk)] = test
        
        for parameter_pk, test in tests.iteritems():
            if sample_data[test] is not None:
                value = MeasuredValue()
                
                if sample_data[test] == "negative":
                    value.value = 0
                elif sample_data[test] == "positive":
                    value.value = 1
                else:
                    if sample_data[test] is not None:
                        value.value = sample_data[test]
                    else:
                        value.value = ''
                    
                value.parameter = Parameter.objects.get(id=parameter_pk)
                value.sample = sample
                value.save()

        # check sms notifications
        send_sms_notifications(sample)
    else:
        logging.debug("no xmlns")

# Register to receive signals each time a Metadata is saved    
post_save.connect(check_and_add_sample, sender=Metadata)
