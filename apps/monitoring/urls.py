from django.urls import path
from . import views

app_name = 'monitoring'
urlpatterns = [
    path('', views.index, name='index'),
    path('board/', views.board, name='board'),
    path('services/<int:pk>/status/<str:status>/', views.update_status, name='update_status'),
    path('assignments/', views.assignments, name='assignments'),
    path('assignments/<int:pk>/', views.assign, name='assign'),
]
