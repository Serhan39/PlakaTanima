from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models import CameraDirection, RelayType, UserRole, WatchlistCategory


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
    relay_type: RelayType = RelayType.NONE
    relay_target: str = ""
    relay_command: str = ""
    relay_pulse_seconds: float = 3.0
    open_categories: str = "allowed,staff"
    direction: CameraDirection = CameraDirection.NONE


class CameraRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    rtsp_url: str
    is_active: bool
    relay_type: RelayType
    relay_target: str
    relay_command: str
    relay_pulse_seconds: float
    open_categories: str
    direction: CameraDirection


class RelayTestResult(BaseModel):
    success: bool
    message: str


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


class ReportSummary(BaseModel):
    date_from: datetime
    date_to: datetime
    total: int
    by_category: dict[str, int]
    by_camera: list[dict]
    by_hour: list[dict]


class ParkingStatus(BaseModel):
    inside: int
    capacity: int
    occupancy_percent: float


class ParkingCapacityUpdate(BaseModel):
    capacity: int
