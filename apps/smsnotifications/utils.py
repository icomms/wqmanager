import httplib, urllib, logging, urllib2, re
from threading import Thread

from django.db import models
from django.db.models.signals import post_save

from smsnotifications.models import SmsNotification, OkMessage
from reporters.models import PersistantConnection

from rapidsms.webui import settings

try:
    import json
except ImportError:
    import simplejson as json

def _send_sms(reporter_id, message_text):
    data = {"uid":  reporter_id,
            "text": message_text
            }
    encoded = urllib.urlencode(data)
    headers = {"Content-type": "application/x-www-form-urlencoded",
               "Accept": "text/plain"}
    try:
        conn = httplib.HTTPConnection("localhost:8000") # TODO: DON'T HARD CODE THIS!
        conn.request("POST", "/ajax/messaging/send_message", encoded, headers)
        response = conn.getresponse()
    except Exception, e:
        # TODO: better error reporting
        raise
    
def _send_clickatell_sms(number, message):    
    user = settings.CLICKATELL_USER
    api_id = settings.CLICKATELL_ID
    password = settings.CLICKATELL_PASSWORD
    
    if number.startswith('+'):
        number = number[1:]
        
    message = urllib2.quote(message)
    url = "http://api.clickatell.com/http/sendmsg?user=%s&password=%s&api_id=%s&to=%s&text=%s" % (user, password, api_id, number, message)    
    
    try:    
        if user:
            response = urllib2.urlopen(url)
            
        logging.debug("sending sms: " + url)
        return True # TODO check response rather
    except:
        False     
        
def _format_message(sample, message_text):
    message_text = message_text.replace('%date%', sample.date_received.strftime("%Y-%m-%d"))
    
    if sample.sampling_point.code:
        message_text = message_text.replace('%sitecode%', sample.sampling_point.code)
    else:
        message_text = message_text.replace('%sitecode%', '')
    
    message_text = message_text.replace('%sitename%', sample.sampling_point.name)
    message_text = message_text.replace('%operatorname%', sample.taken_by.alias)
    
    # look for assessment field names and attempt to substitute in values
    field_names = re.findall('%(.*?)%', message_text)

    # check if there are field names to processes    
    if len(field_names) > 0:
        # check if there are assessment fields on this sample
        if sample.assessment_fields != None and sample.assessment_fields != '':
            
            #load the assessment fields
            assessment_fields = json.loads(sample.assessment_fields)
    
            # attempt to replace each field name
            for field_name in field_names:
                try:
                    message_text = message_text.replace('%' + field_name + '%', assessment_fields[field_name])
                except:
                    pass
    
    return message_text    

def send_sms_notifications(sample):
    from samples.models import ParameterTranslation
    
    notifications = SmsNotification.objects.filter(xform__target_namespace=sample.xform.target_namespace).exclude(is_active=False) # get all notifications with xform namespaces same as sample xform namespace
    failure = False # was there a failed notification?
    
    for notification in notifications:
        if notification.samplingpoint.count() > 0:
            if sample.sampling_point not in notification.samplingpoint.all():
                continue
        
        message_text = _format_message(sample, notification.message_text)
        failed_parms = fails_normal_range(notification, sample)
        messages = []
        
        if len(failed_parms) > 0:
            failure = True
            
            # replace test name var
            if notification.send_message_per_error:
                for parm in failed_parms:
                    pt = ParameterTranslation.objects.filter(parameter=parm, wqmauthority=sample.sampling_point.wqmarea.wqmauthority)
                    
                    if pt.count() > 0:
                        test_name = pt[0].test_name
                    else:
                        test_name = parm.test_name
                        
                    messages.append(message_text.replace('%test%', test_name))                    
            else:
                tests = []
                for parm in failed_parms:
                    pt = ParameterTranslation.objects.filter(parameter=parm, wqmauthority=sample.sampling_point.wqmarea.wqmauthority)
                    
                    if pt.count() > 0:
                        tests.append(pt[0].test_name)
                    else:
                        tests.append(parm.test_name)
                        
                messages.append(message_text.replace('%test%', ", ".join(tests)))                    
                 
            if notification.send_to_operator:
                try:
                    persistant_connection = PersistantConnection.objects.get(reporter=sample.taken_by)
                    
                    if persistant_connection.identity:
                        number = _format_number(sample.sampling_point.wqmarea.wqmauthority.dialing_code, persistant_connection.identity)
                        for message in messages:
                            _send_clickatell_sms(number, message)
                except PersistantConnection.DoesNotExist:
                    pass
    
            for manager in notification.manager.all():
                for message in messages:
                    _send_clickatell_sms(manager.phone_number, message)
                
    if not failure:        
        try:
            persistant_connection = PersistantConnection.objects.get(reporter=sample.taken_by)
            
            if persistant_connection.identity:
                try:
                    message = OkMessage.objects.get(wqmauthority=sample.sampling_point.wqmarea.wqmauthority)
                    message_text = _format_message(sample, message.message_text)
                except OkMessage.DoesNotExist:
                    # fall-back (store in db?)
                    message_text = "Thank you for submitting your water test results"
                                                        
                number = _format_number(sample.sampling_point.wqmarea.wqmauthority.dialing_code, persistant_connection.identity)
                _send_clickatell_sms(number, message_text)                            
        except PersistantConnection.DoesNotExist:                    
            pass
    
def _format_number(dialing_code, number):
    if number.startswith('0'):
        number = number[1:]
        
    if dialing_code:
        number = str(dialing_code) + str(number)
        
    return number

def fails_normal_range(notification, sample):
    from samples.models import MeasuredValue, NormalRange
    failed_parms = []
    
    measured_values = MeasuredValue.objects.filter(sample=sample)
    
    for measured_value in measured_values:
        normalranges = notification.normalrange.filter(value_rule__parameter=measured_value.parameter, wqmauthority=sample.sampling_point.wqmarea.wqmauthority) 
        
        for normalrange in normalranges:            
            # cough, code to work with min/max/average type questions
            # TODO find a better way            
            if str(measured_value.value).find('; ') != -1:
                pair = str(measured_value.value).split('; ')[0].split(' - ')
                minMeasured = pair[0]
                maxMeasured = pair[1]
                
                try:
                    if minMeasured != "(n/a)" and (float(minMeasured) < float(normalrange.minimum) or float(minMeasured) > float(normalrange.maximum)):
                        failed_parms.append(measured_value.parameter)
                    elif maxMeasured != "(n/a)" and (float(maxMeasured) < float(normalrange.minimum) or float(maxMeasured) > float(normalrange.maximum)):
                        failed_parms.append(measured_value.parameter)
                except ValueError, e:
                    logging.debug(e)
                    pass
            else:
                try:
                    if float(measured_value.value) < float(normalrange.minimum) or float(measured_value.value) > float(normalrange.maximum):
                        failed_parms.append(measured_value.parameter)
                        logging.debug("failed: " + measured_value.parameter.test_name)
                except ValueError, e:
                    logging.debug(e)
                    pass
            
    return failed_parms
