import re

from Repositories.access_request_repository import (
    ACCESS_REQUEST_DUPLICATE_EMAIL,
    ACCESS_REQUEST_IP_LIMIT_EXCEEDED,
    access_request_repository as default_access_request_repository,
)
from Services.user_service import ACCOUNT_CATEGORY_ADMIN
from Services.vocabulary_service import HTML_PATTERN, SQL_INJECTION_PATTERN


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
ACCESS_REQUEST_QUEUE_LIMIT = 20
ACCESS_REQUEST_DAILY_IP_LIMIT = 3


class AccessRequestService:
    def __init__(self, access_request_repository=default_access_request_repository):
        self._access_request_repository = access_request_repository

    def create_access_request(self, data, ip_address):
        values, error = self._validate_data(data)
        if error:
            return None, error
        ip_address = self._clean_text(ip_address)
        if not ip_address:
            return None, "IP address is required"

        access_request_id, error = self._access_request_repository.create_access_request_with_guardrails(
            values["name"],
            values["email"],
            values["message"],
            ip_address,
            ACCESS_REQUEST_QUEUE_LIMIT,
            ACCESS_REQUEST_DAILY_IP_LIMIT,
        )
        if error == ACCESS_REQUEST_DUPLICATE_EMAIL:
            return None, "Email already has an active access request"
        if error == ACCESS_REQUEST_IP_LIMIT_EXCEEDED:
            return None, "Too many access requests from this IP address today"
        return self._access_request_repository.get_access_request(access_request_id), None

    def list_access_requests(self, acting_user):
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return None, "Admin account is required"
        return self._access_request_repository.list_access_requests(), None

    def delete_access_request(self, acting_user, access_request_id):
        if not acting_user or acting_user["account_category"] != ACCOUNT_CATEGORY_ADMIN:
            return False, "Admin account is required"
        if not self._access_request_repository.delete_access_request(access_request_id):
            return False, "Access request was not found"
        return True, None

    def _validate_data(self, data):
        name = self._clean_text(data.get("name"))
        email = self._clean_text(data.get("email")).lower()
        message = self._clean_text(data.get("message"))
        honeypot = self._clean_text(data.get("website"))
        fields = [name, email, message]

        if honeypot:
            return None, "Access request was rejected"
        if any(HTML_PATTERN.search(field) or SQL_INJECTION_PATTERN.search(field) for field in fields):
            return None, "HTML tags and SQL statements are not allowed"
        if not name:
            return None, "Name is required"
        if len(name) > 100:
            return None, "Name must be 100 characters or fewer"
        if not email:
            return None, "Email is required"
        if len(email) > 256 or not EMAIL_PATTERN.fullmatch(email):
            return None, "Email must be valid"
        if not message:
            return None, "Message is required"
        if len(message) > 1000:
            return None, "Message must be 1000 characters or fewer"

        return {"name": name, "email": email, "message": message}, None

    def _clean_text(self, value):
        if value is None:
            return ""
        return str(value).strip()


access_request_service = AccessRequestService()
