from django.core.cache import cache
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import Account, User


class AuthenticationTests(APITestCase):
    def setUp(self):
        cache.clear()

    def register(self, email="user@example.com", password="StrongPass123!"):
        return self.client.post(
            reverse("register"),
            {
                "email": email,
                "password": password,
                "first_name": "Test",
                "last_name": "User",
            },
            format="json",
        )

    def test_registration_creates_user_account_and_tokens(self):
        response = self.register()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["balance"], "0.00")
        self.assertTrue(User.objects.filter(email="user@example.com").exists())
        self.assertTrue(Account.objects.filter(user__email="user@example.com").exists())

    def test_registration_rejects_duplicate_email(self):
        self.register()

        response = self.register()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_login_returns_user_and_tokens(self):
        self.register()

        response = self.client.post(
            reverse("token-obtain-pair"),
            {"email": "user@example.com", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.assertEqual(response.data["user"]["email"], "user@example.com")

    def test_login_rejects_invalid_password(self):
        self.register()

        response = self.client.post(
            reverse("token-obtain-pair"),
            {"email": "user@example.com", "password": "WrongPass123!"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        response = self.client.get(reverse("me"))

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_blacklists_refresh_token(self):
        registration = self.register()
        refresh = registration.data["refresh"]
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {registration.data['access']}"
        )

        logout_response = self.client.post(reverse("logout"), {"refresh": refresh})
        refresh_response = self.client.post(
            reverse("token-refresh"),
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(logout_response.status_code, status.HTTP_205_RESET_CONTENT)
        self.assertEqual(refresh_response.status_code, status.HTTP_401_UNAUTHORIZED)
