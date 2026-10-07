from django.urls import path

from . import views

app_name = 'customers'
urlpatterns = [
    path('login/', views.CustomerLoginView.as_view(), name='customer_login'),
    path('login/verify/', views.CustomerVerifyOTPView.as_view(), name='customer_login_verify_otp'),
    path('login/resend/', views.customer_login_resend_otp, name='customer_login_resend_otp'),
    path('register/', views.register_customer, name='register_customer'),
    path('invite/', views.invite_customer_account, name='invite_customer'),
    path('', views.index, name='index'),
    path('<int:pk>/', views.detail, name='detail'),
]
