from django.urls import path
from . import views

app_name = 'audittrail'
urlpatterns = [
	path('', views.index, name='index'),
	path('export/events.csv', views.export_events_csv, name='export_events_csv'),
]
