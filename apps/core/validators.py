import re

from django.core.exceptions import ValidationError


def validate_phone_number(value):
    if value and not re.fullmatch(r"\+?[0-9][0-9 ()-]{5,28}[0-9]", value):
        raise ValidationError("Enter a valid phone number using 7 to 30 characters.")
