import secrets
from functools import wraps

from flask import jsonify, request, session


CSRF_SESSION_KEY = "_csrf_token"


def get_csrf_token():
    token = session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def csrf_token_is_valid(token):
    expected_token = session.get(CSRF_SESSION_KEY)
    return bool(token and expected_token and secrets.compare_digest(token, expected_token))


def validate_csrf_token():
    token = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token")
    if csrf_token_is_valid(token):
        return None
    if request.is_json:
        return jsonify({"error": "Invalid CSRF token"}), 400
    return "Invalid CSRF token"


def csrf_required(route_function):
    @wraps(route_function)
    def wrapper(*args, **kwargs):
        error = validate_csrf_token()
        if error:
            if isinstance(error, str):
                return jsonify({"error": error}), 400
            return error
        return route_function(*args, **kwargs)

    return wrapper
