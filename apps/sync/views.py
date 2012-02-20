import datetime

from django.http import HttpResponse, HttpResponseServerError, HttpResponseBadRequest
from rapidsms.webui.utils import render_to_response
from sync.models import Device
from domain.models import Domain
from wqm.models import WqmAuthority, WqmArea, SamplingPoint
from django.db.models import Q

def list(request, domain_name):
    help = "Please specify a device ID and valid domain name, i.e. /sync/list/&lt;domain_name&gt;?device=&lt;device_id&gt;"
    
    device = request.GET.get("device", None)
    
    if not device:
        return HttpResponse(help)
    
    try:
        device_record = Device.objects.get(device=device)
    except:
        # device not on record, create new one
        device_record = Device(device=device, last_update=None)
        device_record.save()

    domain = False
    
    try:
        domain = Domain.objects.get(name=domain_name)
    except:
        False
    
    if not domain_name or not domain or not domain.wqmauthority:
        return HttpResponse(help)
        
    # record time before fetching records
    update_time = datetime.datetime.utcnow()
        
    # get sample points 
    if device_record.last_update:
        # date comparison        
        points = SamplingPoint.objects.filter(Q(wqmarea__wqmauthority__exact=domain.wqmauthority, modified__gte=device_record.last_update) | Q(wqmarea__wqmauthority__exact=domain.wqmauthority, created__gte=device_record.last_update))
    else:
        # fetch everything if device has no recorded last update time
        points = SamplingPoint.objects.filter(wqmarea__wqmauthority__exact=domain.wqmauthority)    
    
    comma_list = ",".join(str(point.id) for point in points)        
        
    #removeme
    device_record.last_update = update_time
    device_record.save()    
    
    return HttpResponse(comma_list)

def get(request, domain_name):
    id = request.GET.get("id", None)
    
    if not id:
        return HttpResponse("Please specify a sample point ID and valid domain name, i.e. /sync/get/&lt;domain_name&gt;?id=&lt;point_id&gt;")

    try:
        samplepoint = SamplingPoint.objects.get(id=id)
    except:
        return HttpResponse("Invalid sample point ID.")
    
    context = {}
    context['samplepoint'] = samplepoint
    
    return render_to_response(request, 'get_samplepoint.html', context)
