from smsnotifications.models import SmsNotification, Manager, OkMessage
from django.contrib import admin
from hq.models import *

class SmsNotificationAdmin(admin.ModelAdmin):
    list_display = ('description', 'wqmauthority', 'xform', 'modified', 'created')
    search_fields = ('wqmauthority', 'xform', 'manager')
    list_filter = ['wqmauthority', 'manager']

admin.site.register(SmsNotification, SmsNotificationAdmin)

class ManagerAdmin(admin.ModelAdmin):
    list_display = ('wqmauthority', 'name', 'phone_number', 'email', 'is_active')
    
admin.site.register(Manager, ManagerAdmin)

class OkMessageAdmin(admin.ModelAdmin):
    list_display = ('wqmauthority', 'message_text')

admin.site.register(OkMessage, OkMessageAdmin)
