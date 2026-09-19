import os

os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")

from app.config import get_settings
from app.crypto import decrypt_text, deterministic_hash, encrypt_text

get_settings.cache_clear()


def test_encrypt_decrypt_round_trip():
    original = "34 ABC 123"
    token = encrypt_text(original)
    assert token != original
    assert decrypt_text(token) == original


def test_deterministic_hash_is_stable_and_case_insensitive():
    assert deterministic_hash("34 abc 123") == deterministic_hash("34 ABC 123")
