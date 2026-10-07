from django.urls import path
from . import views

app_name = 'reports'
urlpatterns = [
    path('', views.index, name='index'),
    path('sales/daily/', views.daily, name='daily'),
    path('sales/weekly/', views.weekly, name='weekly'),
    path('sales/monthly/', views.monthly, name='monthly'),
    path('sales/annual/', views.annual, name='annual'),
    path('service-sales/', views.service_sales, name='service_sales'),
    path('appointment-status/', views.appointment_status, name='appointment_status'),
    path('staff-workload/', views.staff_workload, name='staff_workload'),
    path('top-services/', views.top_services, name='top_services'),
    path('top-staff/', views.top_staff, name='top_staff'),
    path('<str:report_type>/export/<str:export_format>/', views.export, name='export'),
    path('daily/', views.daily_summary, name='daily_summary'),
]
