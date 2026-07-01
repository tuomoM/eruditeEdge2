import json
import secrets
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi


GOOGLE_AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
GOOGLE_OAUTH_STATE_KEY = "_google_registration_state"
GOOGLE_LOGIN_STATE_KEY = "_google_login_state"


class GoogleOAuthService:
    def __init__(self):
        self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    def create_authorization_url(self, session, client_id, redirect_uri):
        state = secrets.token_urlsafe(32)
        session[GOOGLE_OAUTH_STATE_KEY] = state
        return self._authorization_url(client_id, redirect_uri, state)

    def create_login_authorization_url(self, session, client_id, redirect_uri):
        state = secrets.token_urlsafe(32)
        session[GOOGLE_LOGIN_STATE_KEY] = state
        return self._authorization_url(client_id, redirect_uri, state)

    def validate_registration_state(self, session, state):
        expected_state = session.pop(GOOGLE_OAUTH_STATE_KEY, None)
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            return "Google registration state is invalid"
        return None

    def validate_login_state(self, session, state):
        expected_state = session.pop(GOOGLE_LOGIN_STATE_KEY, None)
        if not state or not expected_state or not secrets.compare_digest(state, expected_state):
            return "Google login state is invalid"
        return None

    def fetch_user_info(self, code, client_id, client_secret, redirect_uri):
        if not code:
            return None, "Google authorization code is missing"

        try:
            token_data = self._post_form(
                GOOGLE_TOKEN_URL,
                {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
            access_token = token_data.get("access_token")
            if not access_token:
                return None, "Google did not return an access token"

            request = Request(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            with urlopen(request, timeout=10, context=self._ssl_context) as response:
                return json.loads(response.read().decode("utf-8")), None
        except HTTPError:
            return None, "Google OAuth request failed"
        except (URLError, TimeoutError, OSError):
            return None, "Google OAuth service could not be reached"
        except (json.JSONDecodeError, ValueError):
            return None, "Google returned invalid OAuth data"

    def _post_form(self, url, form_data):
        body = urlencode(form_data).encode("utf-8")
        request = Request(
            url,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=10, context=self._ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))

    def _authorization_url(self, client_id, redirect_uri, state):
        return (
            GOOGLE_AUTHORIZATION_URL
            + "?"
            + urlencode(
                {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": "openid email profile",
                    "state": state,
                    "prompt": "select_account",
                }
            )
        )


google_oauth_service = GoogleOAuthService()
