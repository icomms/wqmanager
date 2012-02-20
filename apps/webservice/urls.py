from django.conf.urls.defaults import *

urlpatterns = patterns('',                       
    url(r'^webservice/table_names$', 'webservice.views.table_names', name='table_names'),
    url(r'^webservice/added_rows$', 'webservice.views.added_rows', name='added_rows'),
    url(r'^webservice/deleted_rows$', 'webservice.views.deleted_rows', name='deleted_rows'),
    url(r'^webservice/updated_rows$', 'webservice.views.updated_rows', name='updated_rows'),
)
