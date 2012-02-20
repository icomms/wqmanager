from django.conf.urls.defaults import *

urlpatterns = patterns('',                       
    url(r'^sync/list/(?P<domain_name>.*)$', 'sync.views.list', name='list'),
    url(r'^sync/get/(?P<domain_name>.*)$', 'sync.views.get', name='get'),
    (r'', include('receiver.api_.urls')),
)
