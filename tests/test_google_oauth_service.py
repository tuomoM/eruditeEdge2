import unittest
from unittest.mock import patch

from Services.google_oauth_service import GoogleOAuthService


class GoogleOAuthServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.service = GoogleOAuthService()

    def test_fetch_user_info_rejects_missing_code(self):
        google_user, error = self.service.fetch_user_info(
            None,
            "google-client-id",
            "google-client-secret",
            "http://127.0.0.1:5001/register/google/callback",
        )

        self.assertIsNone(google_user)
        self.assertEqual(error, "Google authorization code is missing")

    def test_fetch_user_info_handles_certificate_errors(self):
        with patch("Services.google_oauth_service.urlopen", side_effect=OSError("certificate verify failed")):
            google_user, error = self.service.fetch_user_info(
                "google-code",
                "google-client-id",
                "google-client-secret",
                "http://127.0.0.1:5001/register/google/callback",
            )

        self.assertIsNone(google_user)
        self.assertEqual(error, "Google OAuth service could not be reached")


if __name__ == "__main__":
    unittest.main()
