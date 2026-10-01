from django.urls import path
from . import views

app_name = 'notifications'
urlpatterns = [
    path('', views.index, name='index'),
    path('<int:pk>/read/', views.mark_read, name='mark_read'),
]
