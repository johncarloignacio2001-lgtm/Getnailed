from allauth.account import views as allauth_views
from django.urls import path

from .views import BrandedLoginView


urlpatterns = [
    path("login/", BrandedLoginView.as_view(), name="account_login"),
    path("logout/", allauth_views.logout, name="account_logout"),
    path("reauthenticate/", allauth_views.reauthenticate, name="account_reauthenticate"),
]
