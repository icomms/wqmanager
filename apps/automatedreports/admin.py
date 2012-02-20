from automatedreports.models import EmailReport, DayToSend, DeliveredReport, EmailTemplate
from django.contrib import admin


class DayToSendAdmin(admin.ModelAdmin):
    list_display = ('day', )

admin.site.register(DayToSend, DayToSendAdmin)

class EmailReportAdmin(admin.ModelAdmin):
    list_display = ('description', 'wqmauthority', 'modified', 'created', 'next_send_time', 'is_active')
    search_fields = ('wqmauthority', 'manager')
    list_filter = ['wqmauthority', 'manager']

admin.site.register(EmailReport, EmailReportAdmin)

class DeliveredReportAdmin(admin.ModelAdmin):
    list_display = ('email_report', 'attempted_delivery_at', 'error_message', 'delivery_succeeded')

admin.site.register(DeliveredReport, DeliveredReportAdmin)

admin.site.register(EmailTemplate)