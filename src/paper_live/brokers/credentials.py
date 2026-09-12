"""Parse SecretBroker material into broker-specific credential objects.

Secret store values are expected to be JSON objects (or legacy colon-separated
strings for Toss). Raw material is never logged.
"""

from __future__ import annotations

import json

from .kb import DEFAULT_BUY_ORDER_PATH, KbCredentials
from .toss import TossCredentials


class CredentialParseError(ValueError):
    pass


def parse_toss_credentials(material: str) -> TossCredentials:
    text = material.strip()
    if not text:
        raise CredentialParseError("empty Toss credential material")
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CredentialParseError("Toss credential JSON is invalid") from exc
        try:
            return TossCredentials(
                client_id=str(data["client_id"]),
                client_secret=str(data["client_secret"]),
                account_seq=str(data["account_seq"]),
            )
        except KeyError as exc:
            raise CredentialParseError(f"Toss credential missing field: {exc}") from exc
    parts = text.split(":")
    if len(parts) != 3 or not all(parts):
        raise CredentialParseError("Toss credential must be JSON or client_id:client_secret:account_seq")
    return TossCredentials(parts[0], parts[1], parts[2])


def parse_kb_credentials(material: str) -> KbCredentials:
    text = material.strip()
    if not text:
        raise CredentialParseError("empty KB credential material")
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CredentialParseError("KB credential JSON is invalid") from exc
        try:
            order_path = str(data.get("order_path", DEFAULT_BUY_ORDER_PATH))
            return KbCredentials(str(data["app_key"]), str(data["app_secret"]), order_path)
        except KeyError as exc:
            raise CredentialParseError(f"KB credential missing field: {exc}") from exc
    parts = text.split(":")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        raise CredentialParseError("KB credential must be JSON or app_key:app_secret")
    order_path = parts[2] if len(parts) > 2 and parts[2] else DEFAULT_BUY_ORDER_PATH
    return KbCredentials(parts[0], parts[1], order_path)
