from django.urls import path
from . import views

app_name = 'forecasting'
urlpatterns = [
    path('', views.index, name='index'),
    path('train/', views.train, name='train'),
    path('compare/', views.compare, name='compare'),
    path('runs/<uuid:public_id>/', views.detail, name='detail'),
    path('runs/<uuid:public_id>/evaluate/', views.evaluate, name='evaluate'),
    path('runs/<uuid:public_id>/generate/', views.generate, name='generate'),
    path('runs/<uuid:public_id>/export/', views.export_screen, name='export'),
    path('runs/<uuid:public_id>/export.csv', views.export_csv, name='export_csv'),
]
