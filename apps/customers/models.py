from django.core.validators import validate_email
from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.core.validators import validate_phone_number


class Customer(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="customer_profile",
    )
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone = models.CharField(
        max_length=30,
        blank=True,
        validators=(validate_phone_number,),
    )
    email = models.EmailField(blank=True, validators=(validate_email,))
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("last_name", "first_name", "email")
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="customers_email_ci_unique_nonblank",
            ),
        ]

    def save(self, *args, **kwargs):
        self.first_name = " ".join(self.first_name.split())
        self.last_name = " ".join(self.last_name.split())
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def __str__(self):
        return self.full_name or self.email
