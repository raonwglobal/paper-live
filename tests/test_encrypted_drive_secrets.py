import base64

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
