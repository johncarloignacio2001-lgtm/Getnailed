import secrets
import uuid
from datetime import timedelta

from django.apps import apps as django_apps
from django.conf import settings
from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.core.validators import validate_phone_number


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        return super().normalize_email(email).strip().lower() if email else ""

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        if not email:
            raise ValueError("An email address is required.")
        extra_fields.setdefault("username", email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_active_staff_member", True)
        extra_fields.setdefault("role", User.Role.OWNER)
        extra_fields.setdefault("email_verified_at", timezone.now())

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(email, password, **extra_fields)

    def visible_to(self, actor):
        if actor.is_authenticated and actor.is_owner:
            return self.all()
        if actor.is_authenticated:
            return self.filter(pk=actor.pk)
        return self.none()


class User(AbstractUser):
    class Role(models.TextChoices):
        OWNER = "OWNER", "Owner / Manager"
        CASHIER = "CASHIER", "Cashier"
        STAFF = "STAFF", "Staff"
        CUSTOMER = "CUSTOMER", "Customer"

    email = models.EmailField("email address", unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STAFF)
    phone_number = models.CharField(
        max_length=30,
        blank=True,
        validators=(validate_phone_number,),
    )
    is_active_staff_member = models.BooleanField(default=True)
    email_verified_at = models.DateTimeField(blank=True, null=True)
    is_locked = models.BooleanField(default=False)

    # Fine-grained operational permissions for STAFF. OWNER bypasses these.
    can_use_pos = models.BooleanField(default=False)
    can_manage_bookings = models.BooleanField(default=False)
    can_manage_customers = models.BooleanField(default=False)
    can_assign_services = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def save(self, *args, **kwargs):
        self.email = User.objects.normalize_email(self.email)
        if not self.username:
            self.username = self.email
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.pk and self.role != self.Role.STAFF:
            StaffProfile = django_apps.get_model("services", "StaffProfile")
            if StaffProfile.objects.filter(user_id=self.pk).exists():
                raise ValidationError(
                    {"role": "Delete the linked staff profile before changing this account's role."}
                )

    @property
    def is_owner(self):
        return self.role == self.Role.OWNER or self.is_superuser

    @property
    def is_cashier(self):
        return self.role == self.Role.CASHIER

    @property
    def is_service_staff(self):
        return self.role == self.Role.STAFF

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    def __str__(self):
        return self.get_full_name() or self.email


class AccountActivation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="activations")
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    token_digest = models.CharField(max_length=64, editable=False)
    expires_at = models.DateTimeField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @staticmethod
    def digest(public_id, token):
        return salted_hmac(f"accounts.activation.{public_id}", token).hexdigest()

    @classmethod
    def issue(cls, user):
        now = timezone.now()
        cls.objects.filter(user=user, used_at__isnull=True).update(used_at=now)
        token = secrets.token_urlsafe(32)
        public_id = uuid.uuid4()
        activation = cls.objects.create(
            user=user,
            public_id=public_id,
            token_digest=cls.digest(public_id, token),
            expires_at=now + timedelta(seconds=settings.ACCOUNT_ACTIVATION_TIMEOUT),
        )
        return activation, token

    def is_available(self):
        return (
            self.used_at is None
            and self.expires_at > timezone.now()
            and self.failed_attempts < settings.ACCOUNT_ACTIVATION_MAX_ATTEMPTS
        )

    def matches(self, token):
        return constant_time_compare(self.token_digest, self.digest(self.public_id, token))

    def __str__(self):
        return f"Activation for {self.user.email}"


class MFAConfiguration(models.Model):
    require_internal_user_mfa = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        User,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="mfa_configuration_updates",
    )

    @classmethod
    def get_solo(cls):
        configuration, _ = cls.objects.get_or_create(pk=1)
        return configuration

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "MFA configuration"


class MFARecoveryCode(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="mfa_recovery_codes")
    code_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "code_digest"),
                name="accounts_mfa_recovery_code_unique",
            ),
        ]

    @staticmethod
    def normalize(code):
        return "".join(character for character in code.upper() if character.isalnum())

    @classmethod
    def digest(cls, code):
        key = getattr(settings, "MFA_ENCRYPTION_KEY", "") or os.getenv("MFA_ENCRYPTION_KEY", "") or "kTBqXCXXq2hbIcGaTBaetjnbmtdGR4qWlENY9Kpgjbw"
        return salted_hmac(
            "accounts.mfa.recovery-code",
            cls.normalize(code),
            secret=key,
            algorithm="sha256",
        ).hexdigest()

    @classmethod
    def regenerate_for_user(cls, user):
        codes = []
        for _ in range(settings.MFA_RECOVERY_CODE_COUNT):
            raw = secrets.token_hex(6).upper()
            codes.append(f"{raw[:4]}-{raw[4:8]}-{raw[8:]}")
        with transaction.atomic():
            cls.objects.filter(user=user).delete()
            cls.objects.bulk_create(
                cls(user=user, code_digest=cls.digest(code)) for code in codes
            )
        return codes

    @classmethod
    def consume(cls, user, code):
        if not code:
            return False
        digest = cls.digest(code)
        updated = cls.objects.filter(
            user=user,
            code_digest=digest,
            used_at__isnull=True,
        ).update(used_at=timezone.now())
        return updated == 1

    def __str__(self):
        return f"Recovery code for {self.user.email}"


class LoginDevice(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="login_devices")
    fingerprint_digest = models.CharField(max_length=64)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "fingerprint_digest"),
                name="accounts_login_device_unique",
            ),
        ]

    def __str__(self):
        return f"Login device for {self.user.email}"
