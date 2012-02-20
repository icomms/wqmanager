import os
import sys
import logging

filedir = os.path.dirname(__file__)

rootpath = os.path.join(filedir)

report_archive = (os.path.join(rootpath,'data', 'reports', 'archive'))

sys.path.append(os.path.join(rootpath))
sys.path.append(os.path.join(rootpath,'apps'))
sys.path.append(os.path.join(rootpath,'lib'))

#rapidsms lib stuff
sys.path.append(os.path.join(rootpath,'rapidsms'))
sys.path.append(os.path.join(rootpath,'rapidsms','apps'))
sys.path.append(os.path.join(rootpath,'rapidsms','lib'))
sys.path.append(os.path.join(rootpath,'rapidsms','lib','rapidsms'))
sys.path.append(os.path.join(rootpath,'rapidsms','lib','rapidsms','webui'))


os.environ['RAPIDSMS_INI'] = os.path.join(rootpath,'local.ini')
os.environ['DJANGO_SETTINGS_MODULE'] = 'rapidsms.webui.settings'
os.environ["RAPIDSMS_HOME"] = rootpath

from rapidsms.webui import settings
from automatedreports.models import EmailReport, DayToSend, DeliveredReport
from django.template import Context, loader, Template
from django.core.mail import send_mail, EmailMultiAlternatives
from datetime import timedelta, datetime, date, time
from wqm.models import SamplingPoint, WqmArea
from ui.reports import Reports

# set up a class to hold the data for the email template
class ReportInfo():
    manager = ''
    start_date = datetime.now()
    end_date = datetime.now()
    areas = []
    delivered_id = 0

# set up the next_send_time for any new emailReports
new_email_reports = EmailReport.objects.filter(next_send_time=None).exclude(is_active=False)
for email_report in new_email_reports:
    try:
        email_report.next_send_time = email_report.calc_next_send_time()        
    except:
        pass
    else:    
        email_report.save()

# load list of reports that need to be sent out

scheduledReports = EmailReport.objects.filter(next_send_time__lte=datetime.now()).exclude(is_active=False)

if len(scheduledReports) > 0:
    logging.debug(scheduledReports)

# set up a filename template
#filename_template = Template('wqm_{{report.start_date|date:"d-m-Y"}}_{{report.end_date|date:"d-m-Y"}}_{{report.delivered_id}}.xls')

for sr in scheduledReports:
    for manager in sr.manager.all():
        delivered = DeliveredReport()
        delivered.email_report = sr
        delivered.save()
        
        try:
            areas = sr.area.all()
            start_date = sr.calc_report_start_date()
            end_date = sr.calc_report_end_date()
            if len(areas) == 0:
                areas = sr.wqmauthority.wqmarea_set.all()
            
            report_info = ReportInfo()
            report_info.manager = manager
            report_info.areas = areas
            report_info.start_date = start_date
            # this is just done for display purposes so that the dates displayed are inclusive.
            # when the actual report is generated the start date is inclusive, end date exclusive
            report_info.end_date = end_date + timedelta(days=-1)
            report_info.delivered_id = delivered.id
            
            context = Context({
                'report':report_info,
            })
            
            # create the report            
            sample_points = SamplingPoint.objects.filter(wqmarea__in=areas)
            sample_point_ids = list(sp.id for sp in sample_points)
            
            # old: wb = Reports.get_basic(sample_point_ids, start_date, end_date)
            wb = Reports.get_by_date_received(sample_point_ids, start_date, end_date)
            filename_base = Reports.get_filename(sample_point_ids, report_info.start_date, report_info.end_date)
            filename = '%s_%s.xls' % (filename_base[0:len(filename_base) - 4], report_info.delivered_id)            
            
            filepath = os.path.join(report_archive,filename)
            wb.save(filepath)
            
            
            # set up the email text
            text_temp =  Template(sr.template.template)    
            text_content = text_temp.render(context)
        except Exception, e:
            delivered.error_message = e.__str__()
            delivered.delivery_succeeded = False
            delivered.save()
        else:
            delivered.save()
            
            subject = '%s - %s' % (settings.PROJECT_NAME, sr.description)
            from_email = '%s Reports <%s>' % (settings.PROJECT_NAME, settings.EMAIL_HOST_USER)
            to = manager.email
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
            msg.attach_file(filepath,'application/ms-excel')
            
            try:
                msg.send()
            except Exception, e:
                if e.__str__():
                    delivered.error_message = e.__str__()
                else:
                    delivered.error_message = "Failed to send - unknown error"
                    
                delivered.delivery_succeeded = False
                delivered.save()    
            else:  
                delivered.delivery_succeeded = True
                sr.last_send_time = datetime.now()
                sr.next_send_time = sr.calc_next_send_time()
                sr.save()
                delivered.save()
        
        #TODO: schedule next send
        
