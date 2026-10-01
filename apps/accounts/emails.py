import logging

from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.crypto import salted_hmac


logger = logging.getLogger(__name__)


def consume_email_rate_limit(action, identifier, limit, window):
    digest = salted_hmac(
        f"email-rate-limit.{action}",
        str(identifier),
        algorithm="sha256",
    ).hexdigest()
    key = f"email-rate-limit:{action}:{digest}"
    if cache.add(key, 1, timeout=window):
        return True
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, timeout=window)
        count = 1
    return count <= limit


def send_branded_email(
    recipient,
    subject,
    template_base,
    context=None,
    *,
    rate_action=None,
    rate_identifier=None,
    fail_silently=False,
):
    if rate_action and not consume_email_rate_limit(
        rate_action,
        rate_identifier or recipient,
        settings.SECURITY_EMAIL_LIMIT,
        settings.SECURITY_EMAIL_WINDOW,
    ):
        return False
    context = {**(context or {}), "brand_name": settings.BRAND_NAME}
    plain_message = render_to_string(f"{template_base}.txt", context)
    html_message = render_to_string(f"{template_base}.html", context)
    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            html_message=html_message,
            fail_silently=fail_silently,
        )
    except Exception:
        if not fail_silently:
            raise
        logger.exception(
            "Optional security email delivery failed for template %s.",
            template_base,
        )
        return False
    return True
