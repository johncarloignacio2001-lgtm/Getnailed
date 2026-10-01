from django.urls import path
from . import views

app_name = 'pos'
urlpatterns = [
    path('', views.index, name='index'),
    path('history/', views.history, name='history'),
    path('receipt/<str:receipt_number>/', views.receipt, name='receipt'),
    path('void-approval/', views.void_approval, name='void_approval'),
    path('void-approval/<str:receipt_number>/', views.void_detail, name='void_detail'),
]
