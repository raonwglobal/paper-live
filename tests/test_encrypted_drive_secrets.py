import base64
from datetime import UTC, datetime, timedelta

import pytest

from paper_live.secrets import GoogleDriveSecretStore, SecretAccessDenied, SecretPolicy, SecretRecord


def test_secret_policy_blocks_live_credentials_outside_live():
    policy = SecretPolicy(frozenset({"toss-order"}))
    with pytest.raises(SecretAccessDenied):
        policy.authorize(secret_id="toss-order", mode="PAPER_SANDBOX", capability="order.create")


def test_secret_store_encrypts_and_round_trips_without_drive():
    key = b"k" * 32
    store = GoogleDriveSecretStore.__new__(GoogleDriveSecretStore)
    store.encryption_key = key
    records = [SecretRecord("toss-order", "do-not-log", "tossinvest", "production", ("order.create",))]
    blob = store._encrypt(records)
    assert b"do-not-log" not in blob
    restored = store._decrypt(blob)
    assert restored == records


def test_invalid_key_is_rejected(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_ACCESS_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_DRIVE_SECRET_KEY", base64.urlsafe_b64encode(b"short").decode())
    with pytest.raises(ValueError):
        GoogleDriveSecretStore()


def test_shared_drive_configuration_is_added_to_file_queries(monkeypatch):
    monkeypatch.setenv("GOOGLE_DRIVE_ACCESS_TOKEN", "token")
    monkeypatch.setenv("GOOGLE_DRIVE_SECRET_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())
    monkeypatch.setenv("GOOGLE_DRIVE_SECRET_DRIVE_ID", "drive-123")
    store = GoogleDriveSecretStore()
    params = store._drive_query_params()
    assert "supportsAllDrives=true" in params
    assert "includeItemsFromAllDrives=true" in params
    assert "corpora=drive" in params
    assert "driveId=drive-123" in params


def test_naive_expiration_metadata_is_rejected():
    key = b"k" * 32
    store = GoogleDriveSecretStore.__new__(GoogleDriveSecretStore)
    store.encryption_key = key
    store.file_id = "file-1"
    records = [
        SecretRecord(
            "toss-order",
            "secret",
            "tossinvest",
            "production",
            expires_at=(datetime.now(UTC) + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
        )
    ]
    blob = store._encrypt(records)
    store._find_file_id = lambda: "file-1"
    store._request = lambda *args, **kwargs: blob
    with pytest.raises(RuntimeError, match="must include a timezone"):
        store.get("toss-order")
