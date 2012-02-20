try:
    import json
except ImportError:
    import simplejson as json

from rapidsms.webui import settings
from datetime import datetime
from django.http import HttpResponse, HttpResponseServerError, HttpResponseBadRequest
from rapidsms.webui.utils import render_to_response
from django.db.models import Q

from domain.models import Domain
from wqm.models import WqmAuthority, WqmArea, SamplingPoint
from standards.models import WaterUseType, Standard
from samples.models import ValueRule, Sample, NormalRange, AbnormalRange, MeasuredValue, Parameter

ACCESS_KEY = settings.WEBSERVICE_PASSWORD
SUPERUSER_ID = int(settings.WEBSERVICE_ADMIN_ID)
SUPERUSER_KEY = settings.WEBSERVICE_ADMIN_PASSWORD

ALLOWED_TABLES = [
  'abnormalrange',
  'authorisedsampler',
  'domainlookup',
  'measuredvalue',
  'normalrange',
  'parameter',
  'sample',
  'samplingpoint',
  'smsnotifications',
  'standard',
  'valuerule',
  'waterusetype',
  'wqmarea',
  'wqmauthority'
]

ALLOWED_DOMAINS = map(int, settings.WEBSERVICE_DOMAINS.split(','))

def check_access(request):
    domain = request.GET.get('domain', None)
    key = request.GET.get('key', None)
    
    if domain is None or domain == "" or key is None or key == "":
        return {'success': False, 'error': _error_response("Incorrect access key for domain") }
    
    ok = False
    
    try:
        domain = int(domain)
    except:
        return {'success': False, 'error': _error_response("Incorrect access key for domain") }
    
    if domain == SUPERUSER_ID:
        if key == SUPERUSER_KEY:
            ok = True
    else:
        if key == ACCESS_KEY:
            ok = True
            
    if ok:
        return {'success': True, 'error': None }
    else:    
        return {'success': False, 'error': _error_response("Incorrect access key for domain") }

def table_names(request):      
    key = request.GET.get('key', None)
    
    #skip check for now, because phones in the field don't send access key for this call
    if True or key == SUPERUSER_KEY or key == ACCESS_KEY: 
        return _success_response(ALLOWED_TABLES)
    else:
        return _error_response("Incorrect access key for domain")

def added_rows(request):
    return _fetch_rows(request, 'added')

def updated_rows(request):
    return _fetch_rows(request, 'updated')

def deleted_rows(request):
    return _fetch_rows(request, 'deleted')

def _fetch_rows(request, type):
    result = check_access(request)
    
    if not result['success']:
        return result['error']    

    table = request.GET.get('table', None)
    time = _int_or_zero(request.GET.get('time', None))
    domain = _int_or_zero(request.GET.get('domain', None))    
    
    if table is None or time is None:
        return _error_response("One or more of the following required parameters were not specified: table, time")    
    
    if table not in ALLOWED_TABLES:
        return _error_response("Unknown or forbidden table name specified")
        
    limit = None    
    offset = None      
    
    if request.GET.get('limit', None):
        limit = _int_or_zero(request.GET.get('limit', None))

    if request.GET.get('offset', None):
        offset = _int_or_zero(request.GET.get('offset', None))
        
        # backwards compatibility - match behaviour original android app expects
        if limit is None:
            limit = 1000
            
    data = _normalise_rows(type, table, time, domain) 
    return _success_response(data, limit, offset)

def _int_or_zero(value):
    try:
        return int(value)
    except TypeError, e:
        return 0
    except ValueError, e:
        return 0    
    
def _success_response(data, limit=0, offset=0):
    if limit is None:
        limit = 0
        
    if offset is None:
        offset = 0 
    
    total_count = len(data)
    count = limit
    
    if limit and offset:
        data = data[offset:(limit + offset)]
    elif limit:
        data = data[:limit]
    elif offset:
        data = data[offset:]
        
    count = len(data)    
        
    return _json_response({
        'status': 'success',
        'count': count,
        'total_count': total_count,
        'limit': limit,
        'offset': offset,
        'data': data
    }) 

def _error_response(message):
    return _json_response({
        'status': 'error',
        'count': 0,
        'total_count': 0,
        'limit': 0,
        'offset': 0,
        'data': message
    })

def _json_response(object):
    return HttpResponse(json.dumps(object), content_type='application/json; charset=utf8')

def _normalise_rows(type, table, time, domain):
    domain = int(domain)
     
    data = []
    
    if type == 'deleted':
        return data
    
    # TODO this isn't entirely correct - WQM timestamps are all UTC+0, so we need to adjust the given device time which requires
    # knowing which timezone the device is operating in
    date_query = Q(created__gt=datetime.fromtimestamp(time))
    
    if type == 'updated':
        date_query = Q(modified__gt=datetime.fromtimestamp(time))

    if table == 'abnormalrange':
        rows = AbnormalRange.objects.filter(date_query)    
        
        for row in rows:
            if (domain > 0 and row.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.wqmauthority.id in ALLOWED_DOMAINS):
                data.append({
                    'id': row.id,
                    'description': row.description,
                    'valuerule': row.value_rule.id,
                    'minimum': str(row.minimum),
                    'maximum': str(row.maximum),
                    "remedialaction": row.remedialaction if row.remedialaction is not None else '',
                    "colour": row.color,
                    'wqmauthority': row.wqmauthority.id,
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created)
                })    
    elif table == 'authorisedsampler':
        # not used by android application
        pass
    elif table == 'domainlookup':
        if datetime.fromtimestamp(time) < datetime.strptime("2011-04-19 00:00:00", "%Y-%m-%d %H:%M:%S"):
            data.append({
                'id': 1,
                'key': 'positive',
                'value': 1,
                'parameter': Parameter.objects.get(test_name_short="h2s").id,
                'modified': None,
                'created': str(datetime.now())
            })
            
            data.append({
                'id': 2,
                'key': 'negative',
                'value': 0,
                'parameter': Parameter.objects.get(test_name_short="h2s").id,
                'modified': None,
                'created': str(datetime.now())
            }) 
    elif table == 'measuredvalue':
        rows = MeasuredValue.objects.filter(date_query, parameter__is_decimal=True)    
        
        for row in rows:
            try:
                if (domain > 0 and row.sample.sampling_point.wqmarea.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.sample.sampling_point.wqmarea.wqmauthority.id in ALLOWED_DOMAINS):
                    data.append({
                        'id': row.id,
                        'sample': row.sample.id,
                        'parameter': row.parameter.id,
                        'value': row.value,
                        'modified': str(row.modified) if row.modified is not None else None,
                        'created': str(row.created)
                    })
            except Sample.DoesNotExist:
                pass    
    elif table == 'normalrange':
        rows = NormalRange.objects.filter(date_query)    
        
        for row in rows:
            if (domain > 0 and row.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.wqmauthority.id in ALLOWED_DOMAINS):
                data.append({
                    'id': row.id,
                    'description': row.description,
                    'valuerule': row.value_rule.id,
                    'minimum': str(row.minimum),
                    'maximum': str(row.maximum),
                    'wqmauthority': row.wqmauthority.id,
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created)
                })    
    elif table == 'parameter':
        rows = Parameter.objects.filter(date_query, is_decimal=True)    
        
        for row in rows:
            data.append({
                'id': row.id,
                'testname': row.test_name,
                'units': row.unit,
                'lookuphint': row.lookup_hint,
                'testnameshort': row.test_name_short,                
                'modified': str(row.modified) if row.modified is not None else None,
                'created': str(row.created)
            })
    elif table == 'sample':
        rows = Sample.objects.filter(date_query)    
        
        for row in rows:
            if (domain > 0 and row.sampling_point.wqmarea.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.sampling_point.wqmarea.wqmauthority.id in ALLOWED_DOMAINS):
                data.append({
                    'id': row.id,
                    'samplingpoint': row.sampling_point.id,
                    'takenby': row.taken_by.id,
                    'notes': row.notes,
                    'datetaken': str(row.date_taken.date()),
                    'date_received': str(row.date_received),
                    'datasource': 'xform',
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created),
                })    
    elif table == 'samplingpoint':
        rows = SamplingPoint.objects.filter(date_query)    
        
        for row in rows:
            if (domain > 0 and row.wqmarea.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.wqmarea.wqmauthority.id in ALLOWED_DOMAINS):
                data.append({
                    'id': row.id,
                    'pointname': row.name,
                    'pointcode': row.code,
                    'wqmarea': row.wqmarea.id,
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created),
                    'waterusetype': None,
                    'the_geom': None,
                    'x_coord': row.point.get_x(),
                    'y_coord': row.point.get_y()                                        
                })            
    elif table == 'smsnotifications':
        # not used by android application
        pass    
    elif table == 'standard':
        rows = Standard.objects.filter(date_query)
        
        for row in rows:
            data.append({
                'id': row.id,
                'name': row.name,
                'governingbody': row.governing_body,
                'dateeffective': str(row.date_effective),
                'modified': str(row.modified) if row.modified is not None else None,
                'created': str(row.created)
            })                 
    elif table == 'valuerule':
        rows = ValueRule.objects.filter(date_query)
        
        for row in rows:
            if row.standard is not None: #temporary
                data.append({
                    'id': row.id,
                    'description': row.description,
                    'parameter': row.parameter.id,
                    'standard': row.standard.id if row.standard is not None else None,
                    'waterusetype': row.water_use_type.id if row.water_use_type is not None else None,
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created)
                })       
    elif table == 'waterusetype':
        rows = WaterUseType.objects.filter(date_query)
        
        for row in rows:
            data.append({
                'id': row.id,
                'description': row.description,
                'modified': str(row.modified) if row.modified is not None else None,
                'created': str(row.created)
            })   
    elif table == 'wqmarea':
        rows = WqmArea.objects.filter(date_query)    
        
        for row in rows:
            if (domain > 0 and row.wqmauthority.id == domain) or (domain == SUPERUSER_ID and row.wqmauthority.id in ALLOWED_DOMAINS):
                data.append({
                    'id': row.id,
                    'name': row.name,
                    'wqmauthority': row.wqmauthority.id,
                    'modified': str(row.modified) if row.modified is not None else None,
                    'created': str(row.created)
                })        
    elif table == 'wqmauthority':
        rows = WqmAuthority.objects.filter(date_query)    
        
        for row in rows:
            data.append({
                'id': row.id,
                'name': row.name,
                'modified': str(row.modified) if row.modified is not None else None,
                'created': str(row.created)
            })
            
    return data
