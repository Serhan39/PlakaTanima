from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.models import CameraDirection, RelayType, UserRole, WatchlistCategory


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: UserRole
    can_manage_equipment: bool = False


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.VIEWER
    can_manage_equipment: bool = False


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    role: UserRole
    is_active: bool
    created_at: datetime
    can_manage_equipment: bool


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
    roi_x1: float | None = None
    roi_y1: float | None = None
    roi_x2: float | None = None
    roi_y2: float | None = None


class CameraRoiUpdate(BaseModel):
    roi_x1: float | None = None
    roi_y1: float | None = None
    roi_x2: float | None = None
    roi_y2: float | None = None


class RelayTestResult(BaseModel):
    success: bool
    message: str


class StreamTokenRead(BaseModel):
    token: str


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
    id: int
    plate: str
    confidence: float
    matched_category: WatchlistCategory | None
    detected_at: datetime
    camera_id: int | None = None
    has_snapshot: bool = False


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


class FeatureFlag(BaseModel):
    enabled: bool


class EquipmentZoneCreate(BaseModel):
    name: str


class EquipmentZoneRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    created_at: datetime


class EquipmentGateCreate(BaseModel):
    name: str
    rtsp_url: str = ""
    zone_id: int
    direction: CameraDirection
    line_x1: float = 0.1
    line_y1: float = 0.5
    line_x2: float = 0.9
    line_y2: float = 0.5
    inside_x: float = 0.5
    inside_y: float = 0.1

    @field_validator("direction")
    @classmethod
    def direction_must_be_entry_or_exit(cls, value: CameraDirection) -> CameraDirection:
        if value == CameraDirection.NONE:
            raise ValueError("Kapi yonu 'entry' veya 'exit' olmalidir")
        return value


class EquipmentGateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    rtsp_url: str
    zone_id: int
    direction: CameraDirection
    is_active: bool
    line_x1: float
    line_y1: float
    line_x2: float
    line_y2: float
    inside_x: float
    inside_y: float


class EquipmentGateLineUpdate(BaseModel):
    line_x1: float
    line_y1: float
    line_x2: float
    line_y2: float
    inside_x: float
    inside_y: float


class EquipmentCrossingSubmit(BaseModel):
    gate_id: int
    code: str
    confidence: float = 0.5
    direction: CameraDirection | None = None


class EquipmentCrossingManualSubmit(BaseModel):
    gate_id: int
    code: str
    direction: CameraDirection


class EquipmentStatusRead(BaseModel):
    plate: str
    zone_id: int | None
    zone_name: str
    updated_at: datetime


class EquipmentCrossingRead(BaseModel):
    plate: str
    gate_id: int
    gate_name: str
    zone_id: int
    zone_name: str
    direction: CameraDirection
    confidence: float
    source: str = "camera"
    created_at: datetime


class EquipmentZoneDuration(BaseModel):
    zone_id: int | None
    zone_name: str
    duration_seconds: int


class EquipmentTimeReportEntry(BaseModel):
    plate: str
    breakdown: list[EquipmentZoneDuration]
    total_seconds: int
