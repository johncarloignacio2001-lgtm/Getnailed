from django.conf import settings


def branding(request):
    ctx = {'BRAND_NAME': settings.BRAND_NAME}
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        try:
            from apps.notifications.models import Notification
            ctx['unread_notifications_count'] = Notification.objects.filter(recipient=user, is_read=False).count()
        except Exception:
            ctx['unread_notifications_count'] = 0
    return ctx
