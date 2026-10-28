from django.urls import path
from . import views

app_name = 'notifications'
urlpatterns = [
    path('', views.index, name='index'),
    path('<int:pk>/read/', views.mark_read, name='mark_read'),
    path('messages/', views.messages_inbox, name='messages'),
    path('chatbot/', views.chatbot_api, name='chatbot_api'),
]
