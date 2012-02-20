from django.contrib.gis.db import models
from locations.models import Location, LocationType
from datetime import date, datetime, timedelta
from django.db.models import Count, Avg
from django.contrib.gis.geos import Point
from django.db.models import Q
import sys, string

class WqmLocation(Location):
    """
    For this module, we add a created and modified date to 
    our locations.
    """ 
    modified = models.DateTimeField(blank=True,null=True)
    created = models.DateTimeField(default=datetime.utcnow)
    
    def save(self, *args, **kwargs):
        if self.pk is not None:
            self.modified = datetime.utcnow()
        
        super(WqmLocation, self).save(*args, **kwargs)    

class WqmAuthority(WqmLocation):
    """E.g. a district"""
    domain = models.OneToOneField('domain.Domain', unique=True) # use string model reference to avoid circular import referencing
    dialing_code = models.CharField(max_length=5)
    gmt_offset = models.IntegerField(default=0)
    
    def __unicode__(self):
        return self.domain.name

class WqmArea(WqmLocation):
    wqmauthority = models.ForeignKey(WqmAuthority)    
    
    def save(self, *args, **kwargs):
        self.type = LocationType.objects.get(name="area")
        super(WqmArea, self).save(*args, **kwargs)
        
    def __unicode__(self):
        return self.name

class DeliverySystem(models.Model):
    name = models.CharField(max_length=100)
    
    def __unicode__(self):
        return self.name

class SamplingPoint(WqmLocation):
    """ The point the tests are done """
    
    POINT_TYPE_CHOICES = (                        
        ("ground", "Ground"),
        ("surface","Surface"),
    )
    
    wqmarea = models.ForeignKey(WqmArea)
    point_type = models.CharField(max_length=30, choices=POINT_TYPE_CHOICES, blank=True)
    delivery_system = models.ForeignKey(DeliverySystem, blank=True, null=True)
    treated = models.BooleanField(default=True)
    water_running = models.BooleanField(default=True)
    point = models.PointField(blank=True, null=True)        
    
    objects = models.GeoManager()
    
    def save(self, *args, **kwargs):
        self.type = LocationType.objects.get(name="point")
        
        if self.code == "": #ensure empty codes are set to null
            self.code = None
            
        if self.point is None:
            self.point = Point(0, 0)            
            
        super(SamplingPoint, self).save(*args, **kwargs)
        
    def delete(self, *args, **kwargs):
        self.code = None
        self.active = False
        self.modified = datetime.utcnow()
        self.save()

    def __unicode__(self):
        return self.name

    def get_last_week_samples(self):
        # do some messing around with dates and times to get a range that equals the past 7 days, including today
        today = date.today()

        startDate = today - timedelta(days=6)
        endDate = today + timedelta(days=1)
        
        return self.sample_set.filter(date_taken__gte=startDate, date_taken__lt=endDate)
      
    def get_last_sample(self):
        try:
            return self.sample_set.order_by('-date_taken')[0]
        except IndexError:
            return None

    def get_all_test_parameter_names(self):
        #from samples.models import MeasuredValue
        #return list(mv['parameter__test_name'] for mv in MeasuredValue.objects.filter(sample__sampling_point=self, parameter__is_decimal=True).values('parameter__test_name').order_by('parameter__id').distinct())
        from samples.models import Parameter
        params = Parameter.objects.filter(measuredvalue__sample__sampling_point=self, is_decimal=True).exclude(hide_in_summary=True).order_by('id').distinct()
        
        return list(p.test_name for p in params)
        
    def get_mv_min_max_avg(self):
        SEPERATOR = ';'
        from samples.models import Parameter
        from samples.models import MeasuredValue
        params = Parameter.objects.filter(measuredvalue__sample__sampling_point=self, is_decimal=True).exclude(hide_in_summary=True).order_by('id').distinct()
        
        results = []
        
        for param in params:
            # count the number of measured values that contain a semicolon 
            range_value_count = MeasuredValue.objects.filter(sample__sampling_point=self, value__contains=';', parameter=param).count()
            if range_value_count > 0:
                #print 'isrange'
                # this is a range value, so it needs special handling
                # load all the values ever recorded for this parameter at this sampling point
                values = MeasuredValue.objects.filter(sample__sampling_point=self, value__contains=';', parameter=param)
                
                min = sys.maxint
                max = -sys.maxint - 1
                total_avg = float(0)
                # this isn't the length of the values list because sometimes people might not capture and avg value
                avg_count = 0
                
                for value in values:
                    parts = value.get_range_parts()
                    #print parts
                    if parts['min'] != '' and parts['min'] < min:
                        min = parts['min']
                    if parts['max'] != '' and parts['max'] > max:
                        max = parts['max']
                    if parts['avg'] != '':
                        avg_count += 1
                        total_avg += parts['avg']
                
                if min == sys.maxint:
                    results.append('')
                else:
                    results.append(min)
                
                if max == -sys.maxint - 1:
                    results.append('')
                else:
                    results.append(max)
                    
                if avg_count == 0:
                    results.append('')
                else:
                    results.append(total_avg / float(avg_count))
                
            else:
                #not a range value, handle it normally
                min = ''
                try:
                    #min = MeasuredValue.objects.filter(sample__sampling_point=self, parameter=param).order_by('value')[0].value
                    min = MeasuredValue.objects \
                        .filter(sample__sampling_point=self, parameter=param) \
                        .extra(select={'float_value': 'value + 0'}) \
                        .order_by('float_value')[0].value
                except IndexError:
                    pass
                
                max = ''
                try: 
                    #max = MeasuredValue.objects.filter(sample__sampling_point=self, parameter=param).order_by('-value')[0].value
                    max = MeasuredValue.objects \
                        .filter(sample__sampling_point=self, parameter=param) \
                        .extra(select={'float_value': 'value + 0'}) \
                        .order_by('-float_value')[0].value
                except IndexError:
                    pass
                
                avg = MeasuredValue.objects.filter(sample__sampling_point=self, parameter=param).aggregate(Avg('value'))['value__avg']

                results.append(min)
                results.append(max)
                results.append(avg)
        
        return results

    def h2s_tested(self):
        from samples.models import MeasuredValue
        total = MeasuredValue.objects.filter(sample__sampling_point=self, parameter__test_name='H2S').count()
        return total > 0

    def get_last_month_h2s_success_percent(self):
        from samples.models import MeasuredValue

        today = date.today()
        startDate = today - timedelta(days=30)
        total = MeasuredValue.objects.filter(sample__sampling_point=self, parameter__test_name='H2S', sample__date_taken__gte=startDate, sample__date_taken__lte=today).count()

        if total == 0:
            return None

        success = MeasuredValue.objects.filter(
                Q(sample__sampling_point=self),
                Q(parameter__test_name='H2S'),
                Q(sample__date_taken__gte=startDate),
                Q(sample__date_taken__lte=today),
                Q(value='negative') | Q(value='0')
                ).count()
    
        
        return float(success)/float(total) * 100

    def get_previous_month_h2s_success_percent(self):
        from samples.models import MeasuredValue

        today = date.today()
        startDate = today - timedelta(days=60)
        endDate = today - timedelta(days=30)
        total = MeasuredValue.objects.filter(sample__sampling_point=self, parameter__test_name='H2S', sample__date_taken__gte=startDate, sample__date_taken__lte=endDate).count()

        if total == 0:
            return None

        success = MeasuredValue.objects.filter(
                Q(sample__sampling_point=self),
                Q(parameter__test_name='H2S'),
                Q(sample__date_taken__gte=startDate),
                Q(sample__date_taken__lte=endDate),
                Q(value='negative') | Q(value='0')
                ).count()
        
        
        return float(success)/float(total) * 100

    def guess_top_reporter_alias(self):
        try:
            top_reporter = self.sample_set.values('taken_by__alias').annotate(sample_count=Count('id')).order_by('-sample_count')[0]
        except IndexError:
            return None
        
        return top_reporter['taken_by__alias']
        
    def generate_site_code(self):
        if not self.code:                
            authority_name = self.wqmarea.wqmauthority.name
            point_name = self.name
            
            names_to_split =[authority_name, point_name]
            base = ''
            
            for name in names_to_split:
                name_parts = name.split(' ')
                for i in range(0, 3):
                    # add the first 3 initials of the name to the site code
                    if i < len(name_parts):
                        base += string.capitalize(name_parts[i][0])
                    # if there are less than 3 initials pad with X's
                    else:
                        base += 'X'
                        
            # at this point we have an ideal site code base, so now specify a number to resolve conflicts
            num = 1
                
            while (SamplingPoint.objects.filter(code='%s%02d' % (base, num)).count() > 0):
                num += 1
            
            self.code = '%s%02d' % (base, num)
            return self.code
            
        