import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from app.config import get_settings
from app.models import WatchlistCategory
from app.notifications import maybe_send_alert, send_email

get_settings.cache_clear()


def test_send_email_skips_when_smtp_not_configured():
    assert send_email("Konu", "Govde", ["test@example.com"]) is False


def test_send_email_skips_when_no_recipients():
    assert send_email("Konu", "Govde", []) is False


def test_maybe_send_alert_skips_when_no_category():
    assert maybe_send_alert("34 ABC 12", None, "Ana Giris") is False


def test_maybe_send_alert_skips_when_category_not_in_alert_list():
    assert maybe_send_alert("34 ABC 12", WatchlistCategory.ALLOWED, "Ana Giris") is False


def test_maybe_send_alert_attempts_for_wanted_category():
    # SMTP yapilandirilmadigi icin gonderim yine False doner, ama kategori
    # kontrolunden gecip send_email'e ulasmasi gerekir (exception atmamali).
    assert maybe_send_alert("34 ABC 12", WatchlistCategory.WANTED, "Ana Giris") is False
