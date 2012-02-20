from datetime import timedelta, datetime, date, time
import calendar
from django.db import models

from wqm.models import WqmAuthority, WqmArea
from smsnotifications.models import Manager


class DayToSend(models.Model):    
    day = models.IntegerField(help_text="Day of month to send report on (first day = 1, last day = 31")    
    
    def __unicode__(self):
        return str(self.day)

class EmailTemplate(models.Model):
	name = models.CharField(max_length=50)
	description = models.CharField(max_length=150)
	template = models.TextField()
	
	def __unicode__(self):
		return self.name

class EmailReport(models.Model):
	wqmauthority = models.ForeignKey(WqmAuthority)    
	manager = models.ManyToManyField(Manager)
	template = models.ForeignKey(EmailTemplate)
	description = models.CharField(max_length=50, help_text="Short description of report")
	area = models.ManyToManyField(WqmArea, blank=True)    
	modified = models.DateTimeField(null=True, blank=True)
	created = models.DateTimeField(default=datetime.utcnow)
	DELIVERY_TYPES = (
		('Weekly', 'Weekly'),
		('Custom', 'Specified Days'),
		)
	
	delivery_type = models.CharField(max_length=50, choices=DELIVERY_TYPES)
	
	DAYS_OF_WEEK= (
		(0, 'Sunday'),
		(1, 'Monday'),
		(2, 'Tuesday'),
		(3, 'Wednesday'),
		(4, 'Thursday'),
		(5, 'Friday'),
		(6, 'Saturday'),
		)
	
	weekly_delivery_day = models.IntegerField(choices=DAYS_OF_WEEK,  blank=True, null=True)
	
	day = models.ManyToManyField(DayToSend, blank=True, null=True)
	
	last_send_time = models.DateTimeField(null=True, blank=True)
	next_send_time = models.DateTimeField(null=True, blank=True)
	is_active = models.NullBooleanField(null=True, blank=True)    
	
	def get_frequency_description(self):
		if self.delivery_type == 'Weekly':
			return 'Weekly'
		else:
			if self.day.count() == 1 and \
				self.day.filter(day=1).count() == 1:
				return 'Monthly'
			elif self.day.count() == 2 and \
				self.day.filter(day=1).count() == 1 and \
				self.day.filter(day=16).count() == 1:
					return 'Bi-monthly'
			else:
				return '%d times a month' % self.day.count()

	def calc_next_send_time(self):
		next_send_time = None
		if (self.delivery_type == 'Weekly'):
			today = date.today()
			next_send_time = today + timedelta(days=(int(self.weekly_delivery_day) - today.weekday() -1), weeks=1)
		elif (self.delivery_type == 'Custom'):
			today = date.today()
	
			#find the next reporting day
			for day in self.day.order_by('day'):
				if day.day > today.day:
					next_send_time = date(today.year, today.month, day.day)
					break;
			
			# no reporting day left in this month, so take the first reporting day of next month
			if (next_send_time == None):
				reporting_day = self.day.order_by('day')[0]
				if (today.month == 12):
					next_send_time = date(today.year + 1, 1, reporting_day.day)
				else:
					next_send_time = date(today.year, today.month + 1, reporting_day.day)
		
		return next_send_time
	
	def calc_report_start_date(self):
		start_date = None
		if (self.delivery_type == 'Weekly'):
			today = date.today()
			start_date = today + timedelta(days=(int(self.weekly_delivery_day) - today.weekday() -1), weeks=-1)

		elif (self.delivery_type == 'Custom'):
			today = date.today()
			
			# the first thing to check is if there is only 1 day specified
			if len(self.day.all()) == 1:
				# 31 is a special case, indicating the last day of the month
				if self.day.all()[0].day == 31:
					day = 1
				else:
					day = self.day.all()[0].day
					
				if day > today.day:
					if (today.month == 2):
						start_date = date(today.year -1, 12, day)
					elif (today.month == 1):
						start_date = date(today.year -1, 11, day)
					else:
						start_date = date(today.year, today.month - 2, day)
				else:
					if (today.month == 1):
						start_date = date(today.year -1, 12, day)
					else:
						start_date = date(today.year, today.month - 1, day)
				
			else:				
				#find the previous reporting day
				days = self.day.order_by('-day')
				index = 0
				report_day = None
				
				while True:
					day = days[index]
					if report_day == None and day.day <= today.day:
						# if this is the first day found it will be the end date, so keep going to find the start date
						report_day = day.day
					# otherwise, it's the second day so start date has been found
					elif report_day != None:
						report_day = day.day							
						break
					
					index += 1
					# loop around to the beginning of the list of days					
					if index > len(days) - 1:
						# if we havent picked up a day yet, there are no days less than today
						if report_day == None:
							break;
						index = 0
						
				# if no day was found (because there are no days < current day) pick the 2nd highest day as the start date (highest must be end date)
				if report_day == None:
					report_day = days[1]
				
				#special case, when 31, start date is the first day of the next month
				if (report_day == 31):
					report_day = 1
						
				# check if we need to change months/years
				if (report_day >= today.day):										
					if (today.month == 1):
						start_date = date(today.year -1, 12, 1)
					else:
						start_date = date(today.year, today.month - 1, 1)
				else:
					start_date = date(today.year, today.month, 1)
					
				# make sure that the report day is within the bounds of the given month e.g. no 30th feb
				if report_day > calendar.monthrange(start_date.year, start_date.month)[1]:
					report_day = calendar.monthrange(start_date.year, start_date.month)[1]
					
				start_date = date(start_date.year, start_date.month, report_day)

				
			
		return start_date
	
	
	def calc_report_end_date(self):
		end_date = None
		if (self.delivery_type == 'Weekly'):
			today = date.today()
			end_date = today + timedelta(days=(self.weekly_delivery_day - today.weekday() - 1))
		
		elif (self.delivery_type == 'Custom'):
			today = date.today()
			
			# the first thing to check is if there is only 1 day specified
			if len(self.day.all()) == 1:
				# 31 is a special case, indicating the last day of the month
				if self.day.all()[0].day == 31:
					day = 1
				else:
					day = self.day.all()[0].day
					
				if day > today.day:
					if (today.month == 1):
						end_date = date(today.year -1, 12, day)
					else:
						end_date = date(today.year, today.month - 1, day)
				else:
					end_date = date(today.year, today.month , day)
				
			else:				
				days = self.day.order_by('-day')
				index = 0
				report_day = None
				
				while True:
					day = days[index]
					if report_day == None and day.day <= today.day:
						# if this is the first day found it will be the end date
						report_day = day.day
						break;
					
					index += 1
					# loop around to the beginning of the list of days					
					if index > len(days) - 1:
						# if we havent picked up a day yet, there are no days less than today
						if report_day == None:
							break;
						index = 0
						
				# if no day was found, highest must be end date
				if report_day == None:
					report_day = days[0]
				
				#special case, when 31, end date is the first day of the next month
				if (report_day == 31):
					report_day = 1
						
				# check if we need to change months/years
				if (report_day > today.day):										
					if (today.month == 1):
						end_date = date(today.year -1, 12, 1)
					else:
						end_date = date(today.year, today.month - 1, 1)
				else:
					end_date = date(today.year, today.month, 1)
					
				# make sure that the report day is within the bounds of the given month e.g. no 30th feb
				if report_day > calendar.monthrange(end_date.year, end_date.month)[1]:
					report_day = calendar.monthrange(end_date.year, end_date.month)[1]
					
				end_date = date(end_date.year, end_date.month, report_day)
			
		return end_date
	
	def __unicode__(self):
		return '%s email report for %s' % (self.description, self.wqmauthority)

class DeliveredReport(models.Model):
    email_report = models.ForeignKey(EmailReport)
    attempted_delivery_at = models.DateTimeField(auto_now_add=True) #apparently auto_now_add keyword isn't Good, making a note in case something breaks horribly
    delivery_succeeded = models.BooleanField()
    error_message = models.CharField(max_length=200, null=True)
    error_detail = models.TextField(null=True)
    report_filename = models.CharField(max_length=100, null=True)
    
    def __unicode__(self):
        return '%s for %s in %s' % (self.email_report.description, self.email_report.manager, self.email_report.area)
