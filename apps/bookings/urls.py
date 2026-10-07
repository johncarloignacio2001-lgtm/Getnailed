from django.urls import path
from . import views

app_name = 'bookings'
urlpatterns = [
    path('', views.index, name='index'),
    path('new/services/', views.select_services, name='select_services'),
    path('new/schedule/', views.select_schedule, name='select_schedule'),
    path('api/available-slots/', views.api_available_slots, name='api_available_slots'),
    path('new/review/', views.review, name='review'),
    path('verify/', views.verify, name='verify'),
    path('resend/', views.resend, name='resend'),
    path('status/', views.status_lookup, name='status_lookup'),
    path('access/<str:reference>/<str:token>/', views.public_status, name='public_status'),
    path('access/<str:reference>/<str:token>/cancel/', views.cancel, name='cancel'),
    path('access/<str:reference>/<str:token>/reschedule/', views.reschedule, name='reschedule'),
    path('manage/', views.manage, name='manage'),
    path('calendar/', views.calendar, name='calendar'),
    path('assigned/', views.assigned, name='assigned'),
    path('appointments/<str:reference>/', views.detail, name='detail'),
]
