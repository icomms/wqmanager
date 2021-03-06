from django import template
from xformmanager.models import *
from hq.models import *
from hq.models import *
register = template.Library()
from samples.models import *
from wqm.models import *

xmldate_format= '%Y-%m-%dT%H:%M:%S'
output_format = '%Y-%m-%d %H:%M'

def _get_class(count):
    if count % 2 == 0:
        return "even"
    return "odd"


@register.simple_tag
def get_samples(samples,selected_params):
    title = []
    for sample in samples:
        results = MeasuredValue.objects.filter(sample=sample,parameter__test_name__in = selected_params)
        for result in results:
                if result.parameter.test_name not in title:
                    title.append(result.parameter.test_name)
    ret = ''
    ret += '''<table>\n<thead><tr>
            <th>Date</th>
            <th>Area</th>
            <th>Site code</th>
            <th>Site name</th>
            <th>Reporter</th>
            <th>Comments</th>
            '''
    vars = []
    for i in title:
        ret += '<th>%s</th>'% i
        vars.append(i)
    ret +=       '''
            </tr></thead>
    '''
    count = 1
    
    if samples:
        Data = []
        for sample in samples:
                ret += '\n<tr class="%s">' % _get_class(count)
                point = sample.sampling_point
                results = MeasuredValue.objects.filter(sample=sample, parameter__test_name__in = selected_params)
                dayData = []
                if results:
                    for result in results:
                        if result.sample.id not in dayData:
                            dayData.append(result.sample.id)
                        dayData.append(result.parameter.test_name)
                        dayData.append(result.value)
                    Data.append(dayData)
                    count += 1
                    
                    ret += '<td>%s</td>' % (sample.date_taken.strftime("%Y-%m-%d"))
                    ret += '<td>%s</td>' % (point.wqmarea)
                    ret += '<td>%s</td>' % (point.code)
                    ret += '<td>%s</td>' % (point)
                    ret += '<td>%s</td>' % (sample.taken_by)
                    ret += '<td>%s</td>' % (sample.notes)
                    for i,li in enumerate(Data):
                        for title in vars:
                            if li[0]==result.sample.id:
                                if title in li:
                                    ret += '<td>'
                                    val = int(li.index(title))
                                    val = val + 1
                                    ret += '%s ' % (Data[i][val])
                                    ret += '</td>'
                                else:
                                    ret += '<td>-</td>'
    else:
        ret += '<td>No samples submitted</td>'
    ret += '</tbody></table>'
    return ret
