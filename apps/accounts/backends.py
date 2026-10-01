from django.contrib.auth.backends import ModelBackend


class EligibleUserBackend(ModelBackend):
    def user_can_authenticate(self, user):
        if not super().user_can_authenticate(user):
            return False
        if user.email_verified_at is None or user.is_locked:
            return False
        if user.role in {user.Role.OWNER, user.Role.CASHIER, user.Role.STAFF}:
            return user.is_active_staff_member
        return True
