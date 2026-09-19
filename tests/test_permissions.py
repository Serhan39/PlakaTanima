import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("WATCHLIST_ENCRYPTION_KEY", "Gz3n5J9y8k2p6xQm1wZ7fL0oR4sT8vU2cA6bD9eH3iM=")

import pytest
from fastapi import HTTPException

from app.models import User, UserRole
from app.security import require_equipment_permission


def _user(role: UserRole, can_manage_equipment: bool = False) -> User:
    return User(id=1, username="test", hashed_password="x", role=role, can_manage_equipment=can_manage_equipment)


def test_admin_always_allowed():
    result = require_equipment_permission(user=_user(UserRole.ADMIN))
    assert result.role == UserRole.ADMIN


def test_viewer_without_flag_is_denied():
    with pytest.raises(HTTPException) as exc_info:
        require_equipment_permission(user=_user(UserRole.VIEWER, can_manage_equipment=False))
    assert exc_info.value.status_code == 403


def test_viewer_with_flag_is_allowed():
    result = require_equipment_permission(user=_user(UserRole.VIEWER, can_manage_equipment=True))
    assert result.can_manage_equipment is True


def test_operator_with_flag_is_allowed():
    result = require_equipment_permission(user=_user(UserRole.OPERATOR, can_manage_equipment=True))
    assert result.role == UserRole.OPERATOR
