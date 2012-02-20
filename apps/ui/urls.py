from django.conf.urls.defaults import *

urlpatterns = patterns('',
   (r'^ui/$', 'ui.views.index'),
   (r'^ui/login/$', 'ui.views.uilogin'),
   (r'^ui/logout/$', 'ui.views.uilogout'),
   (r'^ui/map/(?P<domain_id>\d+)$', 'ui.views.map'),
   (r'^ui/reporters/(?P<domain_id>\d+)$', 'ui.views.reporters'),
   (r'^ui/select-domain/', 'ui.views.selectdomain'),
   (r'^ui/report-preview/(?P<domain_id>\d+)$', 'ui.views.report_preview'),
   (r'^ui/report-excel/$', 'ui.views.report_excel'),
   (r'^ui/report/$', 'ui.views.report'),
   (r'^ui/admin/(?P<domain_id>\d+)$', 'ui.views.admin'),
   #(r'^accounts/login/$', 'django.contrib.auth.views.login'),

)
