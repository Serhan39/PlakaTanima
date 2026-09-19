from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import UserRole, WatchlistCategory


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime


class CameraCreate(BaseModel):
    name: str
    location: str = ""
    rtsp_url: str


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    rtsp_url: str
    is_active: bool


class WatchlistCreate(BaseModel):
    plate: str
    category: WatchlistCategory
    note: str = ""


class WatchlistRead(BaseModel):
    id: int
    plate: str
    category: WatchlistCategory
    note: str
    created_at: datetime


class DetectionResult(BaseModel):
    plate: str
    confidence: float
    matched_category: WatchlistCategory | None
    detected_at: datetime
    camera_id: int | None = None
