from django.conf import settings


def branding(request):
    return {'BRAND_NAME': settings.BRAND_NAME}
