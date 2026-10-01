from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model


class SystemHealthViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_superuser(email='owner@example.com', password='password')

    def test_owner_can_view_system_health(self):
        self.client.login(email='owner@example.com', password='password')
        url = reverse('core:system_health')
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'System Health')

    def test_non_owner_cannot_view(self):
        User = get_user_model()
        user = User.objects.create_user(email='staff@example.com', password='password')
        self.client.login(email='staff@example.com', password='password')
        url = reverse('core:system_health')
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 403))
