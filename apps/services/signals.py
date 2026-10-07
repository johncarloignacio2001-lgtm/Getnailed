from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from .models import Service, StaffProfile


@receiver(pre_save, sender=Service)
def remember_previous_service_image(sender, instance, **kwargs):
    if not instance.pk:
        instance._previous_image_name = ""
        return
    previous = sender.objects.filter(pk=instance.pk).only("image").first()
    instance._previous_image_name = previous.image.name if previous and previous.image else ""


@receiver(post_save, sender=Service)
def remove_replaced_service_image(sender, instance, **kwargs):
    previous_name = getattr(instance, "_previous_image_name", "")
    current_name = instance.image.name if instance.image else ""
    if previous_name and previous_name != current_name:
        storage = instance._meta.get_field("image").storage
        transaction.on_commit(lambda: storage.delete(previous_name))


@receiver(post_delete, sender=Service)
def remove_deleted_service_image(sender, instance, **kwargs):
    if instance.image and instance.image.name:
        storage = instance.image.storage
        image_name = instance.image.name
        transaction.on_commit(lambda: storage.delete(image_name))


@receiver(pre_save, sender=User)
def prevent_staff_role_change_with_profile(sender, instance, **kwargs):
    if (
        instance.pk
        and instance.role != User.Role.STAFF
        and StaffProfile.objects.filter(user_id=instance.pk).exists()
    ):
        raise ValidationError(
            {"role": "Delete the linked staff profile before changing this account's role."}
        )



