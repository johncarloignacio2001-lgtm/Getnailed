from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from apps.customers.views import CustomerLoginView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('security/', include('apps.accounts.allauth_urls')),
    path('security/2fa/', include('apps.accounts.mfa_urls')),
    path('captcha/', include('captcha.urls')),
    path('', include('apps.core.urls')),
    path('login/customer/', CustomerLoginView.as_view(), name='customer_login_alt'),
    path('accounts/', include('apps.accounts.urls')),
    path('services/', include('apps.services.urls')),
    path('customers/', include('apps.customers.urls')),
    path('bookings/', include('apps.bookings.urls')),
    path('pos/', include('apps.pos.urls')),
    path('monitoring/', include('apps.monitoring.urls')),
    path('reports/', include('apps.reports.urls')),
    path('forecasting/', include('apps.forecasting.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('audit-trail/', include('apps.audittrail.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
