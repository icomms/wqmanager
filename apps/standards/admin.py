from standards.models import Standard, WaterUseType
from django.contrib import admin

class WaterUseTypeAdmin(admin.ModelAdmin):
    list_display = ('description', 'modified','created')
    search_fields = ('description', 'modified','created')
    list_filter = ['modified']
    fieldsets = (
        (None, {
            'fields' : ('description',)
        }),
    )
admin.site.register(WaterUseType, WaterUseTypeAdmin)

class StandardAdmin(admin.ModelAdmin):
    list_display = ('name','governing_body','date_effective','modified','created')
    search_fields = ('name','governing_body','date_effective','modified','created')
    list_filter = ['governing_body']
    fieldsets = (
        (None, {
            'fields' : ('name','governing_body','date_effective')
        }),
    )    
admin.site.register(Standard, StandardAdmin)

