import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

from fastapi import FastAPI

from app.main import app


def test_app_is_fastapi_instance():
    assert isinstance(app, FastAPI)


def test_expected_routes_registered():
    paths = {route.path for route in app.routes}
    for expected in [
        "/api/auth/login",
        "/api/watchlist",
        "/api/cameras",
        "/api/cameras/{camera_id}/test-relay",
        "/api/detect/image",
        "/api/logs",
        "/api/logs/{log_id}/snapshot",
        "/api/reports/summary",
        "/api/reports/logs",
        "/api/reports/export.csv",
        "/api/reports/send-daily",
        "/api/parking/status",
        "/api/parking/capacity",
        "/api/equipment/feature-status",
        "/api/equipment/zones",
        "/api/equipment/gates",
        "/api/equipment/status",
        "/api/equipment/detect/image",
        "/api/equipment/logs",
        "/api/equipment/time-report",
        "/ws/alerts",
        "/ws/equipment",
    ]:
        assert expected in paths
