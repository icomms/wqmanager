from wqm.models import SamplingPoint, WqmArea
from samples.models import Sample, Parameter, MeasuredValue
import xlwt, time
from datetime import timedelta, datetime, date
from django.template import Context, loader, Template
from django.db.models import Count
from decimal import Decimal

try:
    import json
except ImportError:
    import simplejson as json

class ReportCell():
    value = ''
    is_gray = False
    is_bold = False
    is_date = False
    is_blank = False
    is_number = False
    
    def __init__(self, value='', is_gray=False, is_bold=False, is_date=False, is_blank=False, is_number=False):
        self.value = value
        self.is_gray = is_gray
        self.is_bold = is_bold
        self.is_date = is_date
        self.is_blank = is_blank
        self.is_number = is_number
    
    def __unicode__(self):
        return value
        
class Reports():
    
    def get_report_raw(samples):
        rows = []
        
        # add an empty column list for the table headers which will be filled in later
        rows.append([])
        
        next_param_column = 0        
        params_columns = {}
        
        headers = [            
            'Date Received',
            'Date Taken',
            'Test Type',
            'Area',
            'Site Code',
            'Site Name',
            'Taken By',
            'Comments'
            ]
        
        # write data before additional headers because we dont know what parameter headers we'll need yet
        # (this is why row is set to 1 - row 0 will be headers)
        row = 1
        for sample in samples:
            # add a new row
            rows.append([])
            
            
            # write out the data that will be common across all tests    
            sample_point_data = [                
                sample.date_received,
                sample.date_taken,
                sample.xform.form_display_name, 
                sample.sampling_point.wqmarea.name,
                sample.sampling_point.code,
                sample.sampling_point.name,
                sample.reporter_name,
                sample.notes
            ]
            
            # do the date received and taken first so they can be formatted
            rows[row].append(ReportCell(value=sample_point_data[0], is_date=True))
            rows[row].append(ReportCell(value=sample_point_data[1], is_date=True))
            
            # do the rest, starting with index 2 since dates have just been written out
            for i in range(2,len(sample_point_data)):
                rows[row].append(ReportCell(value=sample_point_data[i]))
            
            # create place holders for empty measured value cells
            for i in range(0, len(params_columns.keys())):
                rows[row].append(ReportCell(is_blank=True))
            
            # common data done, on to measured values
            measured_values = MeasuredValue.objects.filter(sample=sample)
            
            for measured_value in measured_values:
                # vietnam has multiple values stored in one measured value in the format  6.45 - 6.81; 6.63, 14
                # these correspond to min = max;avg, count
                # they must be broken up into multiple columns
                values = []
                header_text = []
                styles = []
                
                param = Parameter.objects.get(pk=measured_value.parameter_id)
                
                # check if this is a multi-value
                if ';' in measured_value.value:
                    # extract values
                    for word in measured_value.value.replace(';',' ').replace(',',' ').split():
                        if (word == '(n/a)'):
                            values.append('')
                            styles.append('gray')
                        else:
                            try:
                                values.append(float(word))
                            except ValueError:
                                pass
                            else:
                                styles.append(None)
                                
    
                    header_text = [
                        '%s (min)' % param.test_name,
                        '%s (max)' % param.test_name,
                        '%s (avg)' % param.test_name,
                        '%s (count)' % param.test_name,                    
                    ]
                    
                    # extracted all the values and set up headers, now set up any addtional styles required
                    if (values[0] != '' and values[1] != '') and (values[0] > values[1]):
                        styles[0] = 'gray'
                        styles[1] = 'gray'
                    
                else:
                    values.append(measured_value.value)
                    header_text.append(param.test_name)
                    styles.append(None)
                                
                # first set up all the param columns and header text
            
                for i in range(len(values)):                        
                    # check if this parameter has been encountered already while processing this report
                    if (header_text[i] not in  params_columns.keys()):
                        # it hasn't been encountered, so figure out the column to use for it
                        # if it's the first parameter check how much common data there is and just
                        # stick it in the next column
                        if(next_param_column == 0):                    
                            next_param_column = len(sample_point_data)
                        
                        # ok, now we know what column we're going to use for this parameter in this report, store it
                        params_columns[header_text[i]] = next_param_column
                        
                        # increment next_param_column for the next parameter that we hit
                        next_param_column += 1
                        
                        # add an item to replace
                        rows[row].append(ReportCell(is_blank=True))
                    
                    # have everything we need, store the value along with style if there is one
                    is_blank =  (values[i] == None) | (values[i] == 'None') | (values[i] == '')
                    is_number = measured_value.parameter.is_decimal
                    
                    if (styles[i] == None):
                        rows[row][params_columns[header_text[i]]] = ReportCell(value=values[i], is_blank=is_blank, is_number=is_number)
                    else:
                        rows[row][params_columns[header_text[i]]] = ReportCell(value=values[i], is_gray=True, is_blank=is_blank, is_number=is_number)
                # end for i in ...
            # end for measured_value in ...
            row += 1
        # end for sample in ...
        
        # loop through the samples a second time, adding all of the assessment_fields. This is done separately to ensure that they
        # appear after the measured values. 
        row = 1
        for sample in samples:
            # make sure the correct column indexes that may be required already exist.
            # they might not because of the dynamic nature of measured values
            
            for i in range(0, ((len(params_columns.keys()) + len(headers))) - len(rows[row])):
                rows[row].append(ReportCell(is_blank=True))
            
            if sample.assessment_fields != None and sample.assessment_fields != '':
                assessment_fields = json.loads(sample.assessment_fields)
                for key in assessment_fields.iterkeys():
                    headerText = key.replace('_', ' ')
                    headerText = headerText[0].upper() + headerText[1:]
                    
                    if headerText not in params_columns.keys():
                        if(next_param_column == 0):                    
                            next_param_column = len(sample_point_data)
                        
                        # ok, now we know what column we're going to use for this parameter in this report, store it
                        params_columns[headerText] = next_param_column
                        
                        # increment next_param_column for the next parameter that we hit
                        next_param_column += 1
                        
                        # add an item to replace
                        rows[row].append(ReportCell(is_blank=True))

                    if assessment_fields[key] and assessment_fields[key] != 'None':    
                        rows[row][params_columns[headerText]] = ReportCell(value=assessment_fields[key].replace('_',' '))
                    else:
                        rows[row][params_columns[headerText]] = ReportCell(value='')
            
            row += 1
        # end for sample in ...
            
        # set up column headers
        # make sure all the columns needed exist
        for i in range(0, ((len(params_columns.keys()) + len(headers))) - len(rows[0])):
            rows[0].append(ReportCell(is_blank=True))            
        
        for i in range(len(headers)):
            rows[0][i] = (ReportCell(value=headers[i], is_bold=True))            
            
        for header_text in params_columns.keys():                
            rows[0][params_columns[header_text]] = (ReportCell(value=header_text, is_bold=True))
            
        return rows
        
    get_report_raw = staticmethod(get_report_raw)
    
    def render_excel(raw_report):
        
        wb = xlwt.Workbook()
        ws = wb.add_sheet('Sheet1')
        
        # create a date style
        excel_date_fmt = 'D-M-YYYY'
        date_style = xlwt.XFStyle()
        date_style.num_format_str = excel_date_fmt
        
        num_style = xlwt.XFStyle()
        #num_style.num_format_str = '#,##0.00'
        num_style.num_format_str = 'general'
        
        gray_num_style = xlwt.easyxf("""
            pattern:
                fore-colour grey25,
                pattern solid
            """)
        gray_num_style.num_format_str = num_style.num_format_str        
        # create a gray cell style
        gray_style = xlwt.easyxf("""
        pattern:
            fore-colour grey25,
            pattern solid
        """)
        
        # Initialize a header style
        style = xlwt.XFStyle()
        font = xlwt.Font()
        font.bold = True
        style.font = font
        
        row_index = 0
        for row in raw_report:
            column_index = 0
            for column in row:
                if not column.is_blank and column.value is not None:
                    if (column.is_date):
                        ws.write(row_index, column_index, column.value, date_style)
                    elif (column.is_bold):
                        ws.write(row_index, column_index, unicode(column.value), style)
                    elif (column.is_number):
                        if column.is_gray:
                            ws.write(row_index, column_index, Decimal(str(column.value)), gray_num_style)
                        else:
                            ws.write(row_index, column_index, Decimal(str(column.value)), num_style)                        
                    elif (column.is_gray):
                        ws.write(row_index, column_index, unicode(column.value), gray_style)     
                    else:
                        ws.write(row_index, column_index, unicode(column.value))
                column_index += 1
                
            row_index += 1
        
        return wb
    render_excel = staticmethod(render_excel)
    
    def get_report_excel(samples):
        raw_report = Reports.get_report_raw(samples)
        return Reports.render_excel(raw_report)
    get_report_excel = staticmethod(get_report_excel)
    

    def render_html(raw_report):
        # first need to get the max column count so we can fill in blank cells to make the table look nicer
        max_column_count = 0
        for row in raw_report:
            if len(row) > max_column_count:
                max_column_count = len(row)
        
        
        html = '<table class="report" cellpadding="0" cellspacing="0">'
        alternating = True
        row_count = 0
        for row in raw_report:
            row_count += 1
            html += '<tr>'
            column_count = 0
            for column in row:
                column_count += 1
                if row_count == 1:
                    html += '<th style="background-color: #BBBBBB;'
                elif alternating:
                    html += '<td style="background-color: #EEEEEE;'
                else:
                    html += '<td style="'
                    
                if column.is_blank:
                    html += '">&nbsp;</td>'
                elif column.is_date:
                    html += '">%s</td>' % column.value        
                elif column.is_bold:
                    html += ' font-weight:bold;">%s</td>' % column.value        
                elif column.is_gray:
                    html += ' background-color:#DDDDDD;">%s</td>' % column.value        
                else:
                    html += '">%s</td>' % column.value
                    
            
            for i in range (0, max_column_count - column_count):
                if alternating:
                    html += '<td style="background-color: #EEEEEE;">&nbsp;</td>'
                else:
                    html += '<td>&nbsp;</td>'
                
            html += '</tr>'
            alternating = not alternating
            
        html += '</table>'
        return html                
    render_html = staticmethod(render_html)
    
    def get_report_html(samples):
        raw_report = Reports.get_report_raw(samples)
        return Reports.render_html(raw_report)
    get_report_html = staticmethod(get_report_html)
    
    def get_basic_for_samples(samples):
        return Reports.get_report_excel(samples)
    get_basic_for_samples = staticmethod(get_basic_for_samples)
    
    def get_basic(sample_point_ids, start_date, end_date):        
        # load up all the samples points to report on
        samples = Sample.objects.filter(sampling_point__id__in=sample_point_ids, date_taken__gte=start_date, date_taken__lte=end_date).order_by('date_taken')
        return Reports.get_basic_for_samples(samples)
    get_basic = staticmethod(get_basic)
    
    def get_by_date_received(sample_point_ids, start_date, end_date):        
        # load up all the samples points to report on
        samples = Sample.objects.filter(sampling_point__id__in=sample_point_ids, date_received__gte=start_date, date_received__lte=end_date).order_by('date_received')
        return Reports.get_basic_for_samples(samples)
    get_by_date_received = staticmethod(get_by_date_received)
    
    def get_test_counts(sample_point_ids, start_date, end_date):
        sp_result = SamplingPoint.objects.filter(id__in=sample_point_ids).order_by('name')

        rows = []
        rows.append([])
        rows[0].append(ReportCell(value='Site', is_bold=True))
        rows[0].append(ReportCell(value='Number of Tests', is_bold=True))
        row = 1
        for sampling_point in sp_result:
            rows.append([])
            rows[row].append(ReportCell(value=sampling_point.name))
            
            sample_count = Sample.objects.filter(sampling_point=sampling_point, date_taken__gte=start_date, date_taken__lte=end_date).count()
            rows[row].append(ReportCell(value=sample_count))
            row += 1
            
        return rows
            
    get_test_counts = staticmethod(get_test_counts)
    
    def get_reporter_test_counts(sample_point_ids, start_date, end_date):
        sp_result = SamplingPoint.objects.filter(id__in=sample_point_ids).order_by('name')

        rows = []
        rows.append([])
        rows[0].append(ReportCell(value='Site', is_bold=True))
        rows[0].append(ReportCell(value='Reporter', is_bold=True))
        rows[0].append(ReportCell(value='Number of Tests', is_bold=True))
        row = 1
        for sampling_point in sp_result:
            # if there are not reporters ever for a site it needs to be added to the report specially
            added_to_report = False
            reporters_with_tests = Sample.objects.filter(sampling_point=sampling_point, date_taken__gte=start_date, date_taken__lte=end_date).order_by('reporter_name').values('reporter_name').annotate(test_count=Count('reporter_name'))
            names = []
            for reporter in reporters_with_tests:
                names.append(reporter['reporter_name'])
                rows.append([])
                rows[row].append(ReportCell(value=sampling_point.name))
                rows[row].append(ReportCell(value=reporter['reporter_name']))
                rows[row].append(ReportCell(value=reporter['test_count']))
                row += 1
                added_to_report = True
            
            reporters_without_tests = Sample.objects.filter(sampling_point=sampling_point).exclude(reporter_name__in=names).order_by('reporter_name').values('reporter_name').annotate(test_count=Count('reporter_name'))
            for reporter in reporters_without_tests:
                names.append(reporter['reporter_name'])
                rows.append([])
                rows[row].append(ReportCell(value=sampling_point.name))
                rows[row].append(ReportCell(value=reporter['reporter_name']))
                rows[row].append(ReportCell(value=0))
                row += 1
                added_to_report = True
                
            if not added_to_report:
                rows.append([])
                rows[row].append(ReportCell(value=sampling_point.name))
                rows[row].append(ReportCell(is_blank=True))
                rows[row].append(ReportCell(is_blank=True))
                row += 1
            # add a blank row for readability
            rows.append([])
            rows[row].append(ReportCell(is_blank=True))
            rows[row].append(ReportCell(is_blank=True))
            rows[row].append(ReportCell(is_blank=True))
            row += 1
        return rows
            
    get_reporter_test_counts = staticmethod(get_reporter_test_counts)    
    
    def get_filename(sample_point_ids, start_date, end_date, report_name=''):        
        # generate filename
        if len(sample_point_ids) == 1:
            sp = SamplingPoint.objects.get(pk=sample_point_ids[0])
            spname = sp.name.replace(' ', '_') .replace('\\','_').replace('//','_').replace('?','_').replace("'","_")
            filename_template = Template('wqm_{%if report_name%}{{report_name}}_{%endif%}{{sp}}_{{start_date}}_{{end_date}}.xls')
            context = Context({
                'report_name' : report_name,
                'start_date':start_date,
                'end_date':end_date,
                'sp': spname,
            })
        else:
            #check if the sampling points are all with in an area
            spoints = SamplingPoint.objects.filter(id__in=sample_point_ids)
            areaName = spoints[0].wqmarea
            
            for spoint in spoints:
                if spoint.wqmarea != areaName:
                    areaName = None
                    break
            
            if areaName != None:
                filename_template = Template('wqm_{%if report_name%}{{report_name}}_{%endif%}{{area}}_{{start_date}}_{{end_date}}.xls')
                context = Context({
                    'report_name' : report_name,
                    'start_date':start_date,
                    'end_date':end_date,
                    'area':areaName.name.replace(' ', '_') .replace('\\','_').replace('//','_').replace('?','_').replace("'","_"),
                })
            else:
                sp = SamplingPoint.objects.filter(pk=sample_point_ids[0])[0]
                filename_template = Template('wqm_{%if report_name%}{{report_name}}_{%endif%}{{domain}}_{{start_date}}_{{end_date}}.xls')
                context = Context({
                    'report_name' : report_name,
                    'start_date':start_date,
                    'end_date':end_date,
                    'domain':sp.wqmarea.wqmauthority.domain,
                })
                
        filename = filename_template.render(context)
        return filename
    
    get_filename = staticmethod(get_filename)
