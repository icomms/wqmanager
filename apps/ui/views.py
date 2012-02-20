# Create your webui views here.
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.contrib.auth import authenticate
from django.contrib.auth import login, logout
from domain.models import Domain
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from wqm.models import SamplingPoint, WqmArea
from samples.models import Sample, Parameter, MeasuredValue, NormalRange
from django.db.models import Max
import xlwt, time, string
from datetime import timedelta, datetime, date
from reports import Reports
from django.template import Context, loader, Template, RequestContext
from reporters.models import Reporter, PersistantConnection
from django.db.models import Q
from ui.models import LogEntry
from smsnotifications.models import Manager, OkMessage, SmsNotification
from xformmanager.models import FormDefModel
from automatedreports.models import EmailReport, DayToSend, EmailTemplate
from django.core.exceptions import ObjectDoesNotExist


def index(request):
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=%s' % request.path)
        
    domain_list = Domain.active_for_user(request.user)
    # if the user has only 1 active domain, skip the select domain page
    if domain_list != None and len(domain_list) == 1:
        return HttpResponseRedirect('/ui/map/%d' % domain_list[0].id)
    else:
        # otherwise, send on to select domain
        return HttpResponseRedirect('/ui/select-domain/')

def uilogin(request):
    log_start_time = datetime.utcnow()
    if request.user.is_authenticated():
        return HttpResponseRedirect('/ui/select-domain')
        
    error = None
    message = None
    
    if request.GET.has_key('action') and request.GET.get('action') == 'logged_out':
        message = "You have been logged out."
        
    
    if request.POST.has_key('txtUsername') and request.POST.has_key('txtPassword'):
        username = request.POST.get('txtUsername')
        password = request.POST.get('txtPassword')
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                login(request, user)
                log_entry = LogEntry()
                log_entry.user = user
                log_entry.timestamp = log_start_time
                log_entry.event_type = 'login'
                log_entry.set_processing_time(log_start_time)
                log_entry.save()
                if request.GET.has_key('next'):
                    return HttpResponseRedirect(request.GET.get('next'))
                else:
                    
                    domain_list = Domain.active_for_user(request.user)
                    # if the user has only 1 active domain, skip the select domain page
                    if domain_list != None and len(domain_list) == 1:
                        return HttpResponseRedirect('/ui/map/%d' % domain_list[0].id)
                    else:
                        # otherwise, send on to select domain
                        return HttpResponseRedirect('/ui/select-domain/')
                # Redirect to a success page.
            else:
                # Return a 'disabled account' error message
                error = 'This account is disabled'
        else:
                # Return an 'invalid login' error message.
                error = 'Invalid login'
                
    # if there's an error to display, clear the message to avoid confusion
    if error != None:
        message = None
    return render_to_response('ui-login.html', {'user' : request.user, 'error' : error, 'message' : message})
    

def uilogout(request):
    log_start_time = datetime.utcnow()
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.event_type = 'logout'
    logout(request)
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return HttpResponseRedirect('/ui/login/?action=logged_out')

def selectdomain(request):
    # user authentication - this is done manually to force the use of a login URL specifc to the UI app
    # dev version of django can do this using @login_required, but 1.2 can't, hence this work-around
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=%s' % request.path)
        
    #check if there is a domain has been posted and redirect
    if request.POST.has_key('domain'):
        return HttpResponseRedirect('/ui/map/' + request.POST['domain'])    
        
    #load up a list of active domains for the logged in user
    domain_list = Domain.objects.filter(  membership__member_type = ContentType.objects.get_for_model(User), 
                                                    membership__member_id = request.user.id, 
                                                    membership__is_active=True, # Looks in membership table
                                                    is_active=True,
                                                    wqmauthority__isnull=False)

    return render_to_response('ui-select-domain.html', {'domain_list': domain_list, 'user' : request.user})
    

def map(request, domain_id):
    log_start_time = datetime.utcnow()
    # user authentication - this is done manually to force the use of a login URL specifc to the UI app
    # dev version of django can do this using @login_required, but 1.2 can't, hence this work-around
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=%s' % request.path)
        
    try:
        # attempt load up the requested domain if the user has access to it
        domain = Domain.objects.filter(  membership__member_type = ContentType.objects.get_for_model(User), 
                                                    membership__member_id = request.user.id, 
                                                    membership__is_active=True, # Looks in membership table
                                                    is_active=True,
                                                    id = domain_id)[0] # Looks in domain table
    except IndexError:
        # if it wasn't loaded it either doesn't exist (in which case the user is poking around with the url)
        # or the user doesn't have access to it. Either way, best to just display access denied so people
        # messing with URLs get as little info as possible.
        #TODO: redirect to an access denied page
        return HttpResponse('access denied - you don\'t have access to this domain id')

    # authentication and authorisation taken care of
    
    # load up the sample points for the given domain
    sample_points = SamplingPoint.objects.filter(wqmarea__wqmauthority__domain = domain, active=1)
    
    template = loader.get_template('ui-map-view.html')
    context = Context({'domain' : domain,
                    'sample_points' : sample_points,
                    'user' : request.user})

    response = HttpResponse(template.render(context))
    
    # create a log entry    
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.event_type = 'page_mapview'
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response

    

    
def reporters(request, domain_id):
    log_start_time = datetime.utcnow()
    # user authentication - this is done manually to force the use of a login URL specifc to the UI app
    # dev version of django can do this using @login_required, but 1.2 can't, hence this work-around
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=%s' % request.path)
        
    try:
        # attempt load up the requested domain if the user has access to it
        domain = Domain.objects.filter(  membership__member_type = ContentType.objects.get_for_model(User), 
                                                    membership__member_id = request.user.id, 
                                                    membership__is_active=True, # Looks in membership table
                                                    is_active=True,
                                                    id = domain_id)[0] # Looks in domain table
    except IndexError:
        # if it wasn't loaded it either doesn't exist (in which case the user is poking around with the url)
        # or the user doesn't have access to it. Either way, best to just display access denied so people
        # messing with URLs get as little info as possible.
        #TODO: redirect to an access denied page
        return HttpResponse('access denied - you don\'t have access to this domain id')

    # authentication and authorisation taken care of
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.post_data = request.POST
    log_entry.event_type = 'page_search'
    
    # check if this is a search and there's something to search on
    if request.POST.has_key('btnSearch') and request.POST.has_key('txtName') and request.POST.get('txtName') != '':
        search_name = request.POST.get('txtName')
        search_tel = ''
        result_type = 'NAME'
        result = Sample.objects.filter(reporter_name__icontains=search_name).filter(sampling_point__wqmarea__wqmauthority__domain__id=domain_id).values('reporter_name').order_by('reporter_name').distinct()
        reporters = list(rep['reporter_name'] for rep in result)        
    elif request.POST.has_key('btnSearch') and request.POST.has_key('txtTel') and request.POST.get('txtTel') != '':
        result_type = 'TEL'
        search_name = ''
        search_tel = request.POST.get('txtTel')
        result = PersistantConnection.objects \
            .filter(identity__icontains=search_tel) \
            .filter(reporter__sample__sampling_point__wqmarea__wqmauthority__domain__id=domain_id) \
            .values('identity').order_by('identity').distinct()
        reporters = list(rep['identity'] for rep in result)
    else:
        reporters = None
        search_name = ''
        search_tel = ''
        result_type = ''
        
    template = loader.get_template('ui-reporters.html')
    context = Context({    'domain' : domain,
                        'user' : request.user,
                        'reporters' : reporters,
                        'search_name' : search_name,
                        'search_tel' : search_tel,
                        'result_type' : result_type,
                        })

    response = HttpResponse(template.render(context))
    
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response

def report_preview(request, domain_id):
    log_start_time = datetime.utcnow()
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=/ui/')
    try:
        # attempt load up the requested domain if the user has access to it
        domain = Domain.objects.filter(  membership__member_type = ContentType.objects.get_for_model(User), 
                                                    membership__member_id = request.user.id, 
                                                    membership__is_active=True, # Looks in membership table
                                                    is_active=True,
                                                    id = domain_id)[0] # Looks in domain table
        
    except IndexError:
        # if it wasn't loaded it either doesn't exist (in which case the user is poking around with the url)
        # or the user doesn't have access to it. Either way, best to just display access denied so people
        # messing with URLs get as little info as possible.
        #TODO: redirect to an access denied page
        return HttpResponse('access denied - you don\'t have access to this domain id')
    
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.post_data = request.POST
    
    if request.POST.has_key('chkReporter') \
        and request.POST.has_key('hdnResultType') \
        and request.POST.has_key('txtStartDate') \
        and request.POST.has_key('txtEndDate'):
        
        start_date = request.POST.get('txtStartDate')
        end_date = request.POST.get('txtEndDate')
        reporters = request.POST.getlist('chkReporter')
        reporter_type = request.POST.get('hdnResultType')

    else:
        return HttpResponse('insufficient parameters')
                
    filename = 'wqm_reporters_%s_%s_%s.xls' % (domain.name.replace(' ', '_') .replace('\\','_').replace('//','_').replace('?','_').replace("'","_"),
                                 start_date,
                                 end_date)
    
    if reporter_type == 'NAME':
        samples = Sample.objects.filter(reporter_name__in=reporters, date_taken__gte=start_date, date_taken__lte=end_date).order_by('date_taken')
        log_entry.event_type = 'rep_prev_reporter_name'
    elif reporter_type == 'TEL':
        samples = Sample.objects.filter(taken_by__connections__identity__in=reporters, date_taken__gte=start_date, date_taken__lte=end_date).order_by('date_taken')
        log_entry.event_type = 'rep_prev_reporter_tel'
    else:
        return HttpResponse('Unknown reporter type supplied')
    
    report_html = Reports.get_report_html(samples)
    
    template = loader.get_template('ui-report-preview.html')
    context = Context({    'domain' : domain,
                        'user' : request.user,
                        'report_table' : report_html,
                        'start_date' : start_date,
                        'end_date' : end_date,
                        'result_type' : reporter_type,
                        'reporters' : ','.join(reporters)
                        })

    response = HttpResponse(template.render(context))
    
    
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response
    
    
def report_excel(request):
    log_start_time = datetime.utcnow()
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=/ui/')
        
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.post_data = request.POST
    
    if request.POST.has_key('chkReporter') \
        and request.POST.has_key('hdnResultType') \
        and request.POST.has_key('txtStartDate') \
        and request.POST.has_key('txtEndDate'):
        
        start_date = request.POST.get('txtStartDate')
        end_date = request.POST.get('txtEndDate')
        reporters = request.POST.get('chkReporter').split(',')
        reporter_type = request.POST.get('hdnResultType')

    else:
        return HttpResponse('insufficient parameters')
                
    filename = 'wqm_reporters_%s_%s.xls' % (start_date, end_date)
    
    if reporter_type == 'NAME':
        samples = Sample.objects.filter(reporter_name__in=reporters, date_taken__gte=start_date, date_taken__lte=end_date).order_by('date_taken')
        log_entry.event_type = 'rep_reporter_name'
    elif reporter_type == 'TEL':
        samples = Sample.objects.filter(taken_by__connections__identity__in=reporters, date_taken__gte=start_date, date_taken__lte=end_date).order_by('date_taken')
        log_entry.event_type = 'rep_reporter_tel'
    else:
        return HttpResponse('Unknown reporter type supplied')
    
    # Create the HttpResponse object with the appropriate XLS header info.
    response = HttpResponse(mimetype="application/ms-excel")
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    
    wb = Reports.get_basic_for_samples(samples)
    wb.save(response)
    
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response
    
def report(request):
    log_start_time = datetime.utcnow()
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=/ui/')

    sample_point_ids = []
    # create a log entry    
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.post_data = request.POST
    
    #check if the post was from an info window (single sample point)
    if request.POST.has_key('btnInfoWindow') \
        and request.POST.has_key('sample_point_id') \
        and request.POST.has_key('txtInfoStartDate') \
        and request.POST.has_key('txtInfoEndDate'):
         
        sample_point_ids.append(request.POST['sample_point_id'])
        start_date = request.POST.get('txtInfoStartDate')
        end_date = request.POST.get('txtInfoEndDate')
        report_type = 'FULL'
         
    elif request.POST.has_key('btnSidePanel')\
        and request.POST.has_key('sample_point') \
        and request.POST.has_key('txtSideStartDate') \
        and request.POST.has_key('txtSideEndDate') \
        and request.POST.has_key('radReportType'):
        
        report_type = request.POST.get('radReportType') 
        start_date = request.POST.get('txtSideStartDate') 
        end_date = request.POST.get('txtSideEndDate') 
        sample_point_ids = request.POST.getlist('sample_point')
    else:
        return HttpResponse('insufficient parameters')
    
    
    
    if report_type == 'SITE_COUNT':
        filename = Reports.get_filename(sample_point_ids, start_date, end_date, 'site-test-count')
        log_entry.event_type = 'rep_site_test_count'
    elif report_type == 'REPORTER_COUNT':
        filename = Reports.get_filename(sample_point_ids, start_date, end_date, 'reporter-test-count')
        log_entry.event_type = 'rep_test_count'
    else:
        filename = Reports.get_filename(sample_point_ids, start_date, end_date)
        log_entry.event_type = 'rep_full'
    
    # Create the HttpResponse object with the appropriate XLS header info.
    response = HttpResponse(mimetype="application/ms-excel")
    response['Content-Disposition'] = 'attachment; filename=%s' % filename
    
    if report_type == 'SITE_COUNT':
        wb = Reports.render_excel(Reports.get_test_counts(sample_point_ids, start_date, end_date))
    elif report_type == 'REPORTER_COUNT':
        wb = Reports.render_excel(Reports.get_reporter_test_counts(sample_point_ids, start_date, end_date))
    else:
        wb = Reports.get_basic(sample_point_ids, start_date, end_date)
        
    wb.save(response)
    
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response

def admin(request, domain_id):
    log_start_time = datetime.utcnow()
    if not request.user.is_authenticated():
        return HttpResponseRedirect('/ui/login/?next=%s' % request.path)
        
    try:
        # attempt load up the requested domain if the user has access to it
        domain = Domain.objects.filter(  membership__member_type = ContentType.objects.get_for_model(User), 
                                                    membership__member_id = request.user.id, 
                                                    membership__is_active=True, # Looks in membership table
                                                    is_active=True,
                                                    id = domain_id)[0] # Looks in domain table
        
    except IndexError:
        # if it wasn't loaded it either doesn't exist (in which case the user is poking around with the url)
        # or the user doesn't have access to it. Either way, best to just display access denied so people
        # messing with URLs get as little info as possible.
        #TODO: redirect to an access denied page
        return HttpResponse('access denied - you don\'t have access to this domain id')
        
    message = ''
    manager_id = ''
    notification_id = ''
    email_report_id = ''
    
    # check if this is a post and save anything required
    #if request.POST.has_key('btnInfoWindow') 
    
    # check if general settings must be saved
    if request.POST.has_key('txtOkMessage'):
        try:        
            okmessage = OkMessage.objects.get(wqmauthority = domain.wqmauthority).message_text
        except ObjectDoesNotExist:
            okmessage = OkMessage(wqmauthority = domain.wqmauthority)
        okmessage.message_text = request.POST.get('txtOkMessage')
        okmessage.save()
        message = 'General settings saved successfully.'
        
    # check if a manager must be saved
    elif request.POST.has_key('manager-id'):
        manager_id = request.POST.get('manager-id')
        if manager_id == '':
            manager = Manager()
            manager.wqmauthority = domain.wqmauthority
            manager.is_active = True
            message = 'A new manager has been added and is highlighted below.'
        else:
            manager = Manager.objects.get(wqmauthority = domain.wqmauthority, id=manager_id)
            message = 'A manager has been modified and is highlighted below.'
            
        manager.name = request.POST.get('manager-name')
        manager.phone_number = request.POST.get('manager-telephone')
        manager.email = request.POST.get('manager-email')
        manager.save()
        manager_id = manager.id
    
    # check if a manager must be deleted
    elif request.POST.has_key('manager-delete-id'):
        manager_delete_id = request.POST.get('manager-delete-id')
        manager = Manager.objects.get(wqmauthority = domain.wqmauthority, id=manager_delete_id)
        manager.is_active = False
        manager.save()
        message = 'Manager deleted.'
    
    # otherwise check if a notification must be saved
    elif request.POST.has_key('notification-id'):
        notification_id = request.POST.get('notification-id')
        if notification_id == '':
            notification = SmsNotification()
            notification.wqmauthority = domain.wqmauthority
            notification.is_active = True
            message = 'A new notification has been added and is highlighted below.'
        else:
            notification = SmsNotification.objects.get(wqmauthority = domain.wqmauthority, id=notification_id)
            message = 'A notification has been modified and is highlighted below.'
            
        notification.description = request.POST.get('notification-description')
        notification.message_text = request.POST.get('notification-messagetext')
        
        # need to figure out which xform to link up
        xform_ns = request.POST.get('notification-xform')
        xform = FormDefModel.objects.filter(domain = domain, target_namespace = xform_ns).order_by('-id')[0]
        notification.xform = xform        
        
        # send one message per error
        per_error = request.POST.get('notification-sendpererror')
        notification.send_message_per_error = (per_error == 'SEND_MANY')
        
        # send to operator
        to_op = request.POST.get('notification-sendtooperator')
        notification.send_to_operator = (to_op == 'TO_OPERATOR')
        
        # this is required - need a PK value to create many-to-many relationships
        notification.save()
        # normal ranges
        if request.POST.get('notification-selected-normalranges') != '':
            nrs = request.POST.get('notification-selected-normalranges').split(',')
            if len(nrs) > 0:
                selected_normal_ranges = NormalRange.objects.filter(wqmauthority = domain.wqmauthority, id__in=nrs)
                notification.normalrange = selected_normal_ranges
            else: notification.normalrange.clear()
        else: notification.normalrange.clear()
            
        # sampling points
        if request.POST.get('notification-selected-samplingpoints') != '':
            sps = request.POST.get('notification-selected-samplingpoints').split(',')
            if len(sps) > 0:
                selected_sampling_points = SamplingPoint.objects.filter(wqmarea__wqmauthority = domain.wqmauthority, id__in=sps)
                notification.samplingpoint = selected_sampling_points
            else: notification.samplingpoint.clear()
        else: notification.samplingpoint.clear()
        
        # managers
        if request.POST.get('notification-selected-managers') != '':
            ms = request.POST.get('notification-selected-managers').split(',')
            if len(ms) > 0:
                selected_managers = Manager.objects.filter(wqmauthority = domain.wqmauthority, id__in=ms)
                notification.manager = selected_managers
                
                notification.save()
                notification_id = notification.id
            else: notification.manager.clear()
        else: notification.manager.clear()
            
    # check if a notification must be deleted
    elif request.POST.has_key('notification-delete-id'):
        notification_delete_id = request.POST.get('notification-delete-id')
        notification = SmsNotification.objects.get(wqmauthority = domain.wqmauthority, id=notification_delete_id)
        notification.is_active = False
        notification.save()
        message = 'Notification deleted.'
        
        
    # check if an email_report must be saved
    elif request.POST.has_key('email_report-id'):
        email_report_id = request.POST.get('email_report-id')
        if email_report_id == '':
            email_report = EmailReport()
            email_report.wqmauthority = domain.wqmauthority
            email_report.is_active = True
            message = 'A new email report has been added and is highlighted below.'
        else:
            email_report = EmailReport.objects.get(wqmauthority = domain.wqmauthority, id=email_report_id)
            message = 'A email report has been modified and is highlighted below.'
            
        email_report.description = request.POST.get('email_report-description')
        email_report.template_id = request.POST.get('email_report-template')
        
        #must save in case we need to do many-to-many for days
        email_report.save()
        
        delivery_type = request.POST.get('email_report-type')
        if delivery_type == 'WEEKLY':
            email_report.delivery_type = 'Weekly'
            email_report.weekly_delivery_day = request.POST.get('email_report-delivery_day')
        elif delivery_type == 'MONTHLY':
            email_report.delivery_type = 'Custom'
            email_report.day.clear()
            email_report.day.add(DayToSend.objects.get(id=1))        
        elif delivery_type == 'BIMONTHLY':
            email_report.delivery_type = 'Custom'
            email_report.day.clear()
            email_report.day.add(DayToSend.objects.get(id=1))
            email_report.day.add(DayToSend.objects.get(id=16))        
        elif delivery_type == 'CUSTOM':
            email_report.delivery_type = 'Custom'
            if request.POST.get('email_report-selected-days') != '':
                selected_days = request.POST.get('email_report-selected-days').split(',')
                if len(selected_days) > 0:
                    selected_day_objects = DayToSend.objects.filter(id__in=selected_days)
                    email_report.day = selected_day_objects
        
        
        if request.POST.get('email_report-selected-managers') != '':
            selected_managers = request.POST.get('email_report-selected-managers').split(',')
            if len(selected_managers) > 0:
                selected_manager_objects = Manager.objects.filter(id__in=selected_managers)
                email_report.manager = selected_manager_objects
                
        if request.POST.get('email_report-selected-areas') != '':
            selected_areas = request.POST.get('email_report-selected-areas').split(',')
            if len(selected_areas) > 0:
                selected_area_objects = WqmArea.objects.filter(id__in=selected_areas)
                email_report.area = selected_area_objects            
            else: email_report.area.clear()
        else: email_report.area.clear()
            
        email_report.save()
        email_report.next_send_time = email_report.calc_next_send_time()       
        email_report.save()
        email_report_id = email_report.id
    
    # check if a email_report must be deleted
    elif request.POST.has_key('email_report-delete-id'):
        email_report_delete_id = request.POST.get('email_report-delete-id')
        email_report = EmailReport.objects.get(wqmauthority = domain.wqmauthority, id=email_report_delete_id)
        email_report.is_active = False
        email_report.save()
        message = 'Email report deleted.'

    try:        
        okmessage = OkMessage.objects.get(wqmauthority = domain.wqmauthority).message_text
    except ObjectDoesNotExist:
        okmessage = ''        
    
    managers = Manager.objects.filter(wqmauthority = domain.wqmauthority).exclude(is_active=False)
    notifications = SmsNotification.objects.filter(wqmauthority = domain.wqmauthority).exclude(is_active=False)
    email_reports = EmailReport.objects.filter(wqmauthority = domain.wqmauthority).exclude(is_active=False)
    email_templates = EmailTemplate.objects.all()
    days = DayToSend.objects.all().order_by('day')
    areas = WqmArea.objects.filter(wqmauthority = domain.wqmauthority)
    delivery_days = EmailReport.DAYS_OF_WEEK
    
    
    normal_ranges = NormalRange.objects.filter(wqmauthority = domain.wqmauthority)
    sampling_points = SamplingPoint.objects.filter(wqmarea__wqmauthority = domain.wqmauthority)
    
    
    xforms = FormDefModel.objects.filter(domain = domain).values('target_namespace', 'form_display_name').distinct()
    
    template = loader.get_template('ui-admin.html')
    context = RequestContext(request,{'domain' : domain,
                        'user' : request.user,
                        'managers' : managers,
                        'modified_manager_id' : manager_id,
                        'okmessage': okmessage,
                        'notifications' : notifications,
                        'modified_notification_id' : notification_id,
                        'email_reports' : email_reports,
                        'days': days,
                        'areas' : areas,
                        'email_templates':email_templates,
                        'delivery_days' : delivery_days,
                        'modified_email_report_id' : email_report_id,
                        'normal_ranges' : normal_ranges,
                        'sampling_points' : sampling_points,
                        'xforms' : xforms,
                        'message' : message,
                        })

    response = HttpResponse(template.render(context))
    
    # create a log entry    
    log_entry = LogEntry()
    log_entry.user = request.user
    log_entry.timestamp = log_start_time
    log_entry.event_type = 'page_admin'
    log_entry.set_processing_time(log_start_time)
    log_entry.save()
    
    return response