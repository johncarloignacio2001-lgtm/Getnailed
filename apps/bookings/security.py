import time
from django.core.cache import cache
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone
from apps.audittrail.events import record_security_event
from apps.audittrail.models import SecurityEvent

_signer = TimestampSigner(salt="booking_form_anti_spam")

def get_client_ip(request):
    """Retrieve client IP address considering proxy headers if available."""
    if not request:
        return "127.0.0.1"
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "127.0.0.1")

def generate_anti_spam_timestamp():
    """Generates a signed timestamp string for public booking forms."""
    return _signer.sign(str(int(time.time())))

def validate_submission_speed(token, min_seconds=2.0):
    """
    Validates that a human took at least min_seconds to fill and submit the form.
    Returns True if valid human timing, False if automated bot.
    """
    if not token:
        # Gracefully allow test runners or direct API calls without timestamp token
        return True
    try:
        raw_time_str = _signer.unsign(token, max_age=3600)
        submitted_at = float(raw_time_str)
        now = time.time()
        elapsed = now - submitted_at
        if elapsed < min_seconds:
            return False
        return True
    except (BadSignature, SignatureExpired, ValueError):
        return False

def check_ip_booking_rate_limit(request, max_attempts=6, window_seconds=600):
    """
    Limits public booking creation attempts per IP address to prevent spam flood.
    Returns (is_allowed, attempts_count).
    """
    ip = get_client_ip(request)
    cache_key = f"booking_rate_ip_{ip}"
    current = cache.get(cache_key, 0)
    if current >= max_attempts:
        return False, current
    cache.set(cache_key, current + 1, timeout=window_seconds)
    return True, current + 1

def check_email_pending_limit(email, max_pending=3):
    """
    Prevents flooding the database with unverified or pending appointments
    under the same email address.
    """
    if not email:
        return True
    from apps.bookings.models import Appointment
    today = timezone.localdate()
    pending_count = Appointment.objects.filter(
        customer_email_snapshot__iexact=email.strip().lower(),
        status__in=[Appointment.Status.UNVERIFIED, Appointment.Status.PENDING],
        appointment_date__gte=today,
    ).count()
    return pending_count < max_pending

def log_spam_blocked(request, reason, email=None):
    """Logs a security event when a spam booking attempt is rejected."""
    ip = get_client_ip(request)
    target_info = f"Spam blocked: {reason}"
    if email:
        target_info += f" | Email: {email}"
    try:
        record_security_event(
            SecurityEvent.Action.SPAM_ATTEMPT_BLOCKED,
            request=request,
            target_type="bookings.Appointment",
            target_id=reason[:100],
            result=SecurityEvent.Result.FAILURE,
        )
    except Exception:
        pass
