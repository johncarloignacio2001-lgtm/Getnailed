import logging
import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.accounts.emails import send_branded_email
from apps.accounts.models import User

logger = logging.getLogger(__name__)

SESSION_KEY_USER_ID = "customer_otp_user_id"
SESSION_KEY_DIGEST = "customer_otp_digest"
SESSION_KEY_EXPIRES_AT = "customer_otp_expires_at"
SESSION_KEY_SENT_AT = "customer_otp_sent_at"
SESSION_KEY_ATTEMPTS = "customer_otp_attempts"
SESSION_KEY_REMEMBER = "customer_otp_remember"
SESSION_KEY_NEXT = "customer_otp_next"

OTP_EXPIRY_MINUTES = 10
OTP_RESEND_COOLDOWN_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def mask_email(email: str) -> str:
    """Mask email for privacy display, e.g. godzu1890@gmail.com -> g*****0@gmail.com."""
    if not email or "@" not in email:
        return email or ""
    user_part, domain = email.split("@", 1)
    if len(user_part) <= 2:
        masked_user = user_part[0] + "*"
    else:
        masked_user = user_part[0] + ("*" * (len(user_part) - 2)) + user_part[-1]
    return f"{masked_user}@{domain}"


def generate_otp_code() -> str:
    """Generate a random 6-digit numeric string."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp_code(code: str) -> str:
    """Derive HMAC digest for the OTP code so plaintext isn't stored in session."""
    return salted_hmac("customer.login.otp", str(code).strip()).hexdigest()


def send_otp_email(user: User, code: str) -> bool:
    """Send login OTP to customer's Gmail."""
    try:
        return send_branded_email(
            user.email,
            f"Your {settings.BRAND_NAME} login verification code",
            "accounts/emails/customer_login_otp",
            {
                "user": user,
                "code": code,
                "expires_minutes": OTP_EXPIRY_MINUTES,
            },
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send customer login OTP email to %s", user.email)
        return False


def initiate_customer_otp(request, user: User, next_url: str = "", remember: bool = False):
    """Start the customer OTP verification process in session and send email."""
    code = generate_otp_code()
    digest = hash_otp_code(code)
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    request.session[SESSION_KEY_USER_ID] = user.pk
    request.session[SESSION_KEY_DIGEST] = digest
    request.session[SESSION_KEY_EXPIRES_AT] = expires_at.isoformat()
    request.session[SESSION_KEY_SENT_AT] = now.isoformat()
    request.session[SESSION_KEY_ATTEMPTS] = 0
    request.session[SESSION_KEY_REMEMBER] = bool(remember)
    request.session[SESSION_KEY_NEXT] = next_url or ""
    request.session.modified = True

    sent = send_otp_email(user, code)
    return sent


def get_pending_customer_user(request):
    """Return the pending User object or None if no valid pending session exists."""
    user_id = request.session.get(SESSION_KEY_USER_ID)
    if not user_id:
        return None
    try:
        user = User.objects.get(pk=user_id, role=User.Role.CUSTOMER, is_active=True)
        return user
    except User.DoesNotExist:
        clear_customer_otp_session(request)
        return None


def verify_customer_otp(request, submitted_code: str):
    """
    Verify the entered OTP code.
    Returns: (is_valid: bool, user: User|None, error_message: str|None)
    """
    user = get_pending_customer_user(request)
    if not user:
        return False, None, "Login session expired. Please sign in again."

    stored_digest = request.session.get(SESSION_KEY_DIGEST)
    expires_str = request.session.get(SESSION_KEY_EXPIRES_AT)
    attempts = request.session.get(SESSION_KEY_ATTEMPTS, 0)

    if not stored_digest or not expires_str:
        clear_customer_otp_session(request)
        return False, None, "Login session expired. Please sign in again."

    if attempts >= OTP_MAX_ATTEMPTS:
        clear_customer_otp_session(request)
        return False, None, "Too many incorrect attempts. Please sign in again."

    try:
        expires_at = datetime.fromisoformat(expires_str)
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at)
    except Exception:
        clear_customer_otp_session(request)
        return False, None, "Invalid verification session. Please sign in again."

    if timezone.now() > expires_at:
        return False, None, "The verification code has expired. Please request a new one."

    clean_code = (submitted_code or "").strip()
    submitted_digest = hash_otp_code(clean_code)

    if not constant_time_compare(submitted_digest, stored_digest):
        attempts += 1
        request.session[SESSION_KEY_ATTEMPTS] = attempts
        request.session.modified = True
        if attempts >= OTP_MAX_ATTEMPTS:
            clear_customer_otp_session(request)
            return False, None, "Too many incorrect attempts. Please sign in again."
        remaining = OTP_MAX_ATTEMPTS - attempts
        return False, None, f"Invalid code. You have {remaining} attempt{'s' if remaining != 1 else ''} remaining."

    # Success: code matched
    next_url = request.session.get(SESSION_KEY_NEXT, "")
    remember = request.session.get(SESSION_KEY_REMEMBER, False)
    clear_customer_otp_session(request)
    return True, user, {"next_url": next_url, "remember": remember}


def resend_customer_otp(request):
    """
    Resend a fresh OTP to the pending customer.
    Returns: (success: bool, message: str)
    """
    user = get_pending_customer_user(request)
    if not user:
        return False, "Login session expired. Please sign in again."

    sent_str = request.session.get(SESSION_KEY_SENT_AT)
    if sent_str:
        try:
            sent_at = datetime.fromisoformat(sent_str)
            if timezone.is_naive(sent_at):
                sent_at = timezone.make_aware(sent_at)
            elapsed = (timezone.now() - sent_at).total_seconds()
            if elapsed < OTP_RESEND_COOLDOWN_SECONDS:
                remaining_wait = int(OTP_RESEND_COOLDOWN_SECONDS - elapsed)
                return False, f"Please wait {remaining_wait} seconds before requesting another code."
        except Exception:
            pass

    code = generate_otp_code()
    digest = hash_otp_code(code)
    now = timezone.now()
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    request.session[SESSION_KEY_DIGEST] = digest
    request.session[SESSION_KEY_EXPIRES_AT] = expires_at.isoformat()
    request.session[SESSION_KEY_SENT_AT] = now.isoformat()
    request.session[SESSION_KEY_ATTEMPTS] = 0
    request.session.modified = True

    sent = send_otp_email(user, code)
    if not sent:
        return False, "Could not send verification email. Please check your network or try again."

    return True, f"A new verification code was sent to {mask_email(user.email)}."


def clear_customer_otp_session(request):
    """Remove customer OTP variables from session."""
    keys = [
        SESSION_KEY_USER_ID,
        SESSION_KEY_DIGEST,
        SESSION_KEY_EXPIRES_AT,
        SESSION_KEY_SENT_AT,
        SESSION_KEY_ATTEMPTS,
        SESSION_KEY_REMEMBER,
        SESSION_KEY_NEXT,
    ]
    for key in keys:
        request.session.pop(key, None)
    request.session.modified = True
