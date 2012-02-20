from ui.models import LogEntry
from django.contrib import admin

class LogEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'timestamp', 'event_type', 'processing_time_ms')
    search_fields = ('user', 'event_type')
    list_filter = ['user', 'event_type']
    readonly_fields = ('user', 'timestamp', 'event_type', 'processing_time_ms', 'post_data')

admin.site.register(LogEntry, LogEntryAdmin)
