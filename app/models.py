import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class WatchlistCategory(str, enum.Enum):
    ALLOWED = "allowed"
    WANTED = "wanted"
    STAFF = "staff"
    BLACKLIST = "blacklist"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.VIEWER)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RelayType(str, enum.Enum):
    NONE = "none"
    HTTP = "http"
    TCP = "tcp"
    MODBUS_TCP = "modbus_tcp"


class CameraDirection(str, enum.Enum):
    NONE = "none"
    ENTRY = "entry"
    EXIT = "exit"


class Camera(Base):
    __tablename__ = "cameras"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    location: Mapped[str] = mapped_column(String(255), default="")
    rtsp_url: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    relay_type: Mapped[RelayType] = mapped_column(Enum(RelayType), default=RelayType.NONE)
    relay_target: Mapped[str] = mapped_column(String(255), default="")
    relay_command: Mapped[str] = mapped_column(String(255), default="")
    relay_pulse_seconds: Mapped[float] = mapped_column(Float, default=3.0)
    open_categories: Mapped[str] = mapped_column(String(255), default="allowed,staff")
    direction: Mapped[CameraDirection] = mapped_column(Enum(CameraDirection), default=CameraDirection.NONE)


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    plate_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category: Mapped[WatchlistCategory] = mapped_column(Enum(WatchlistCategory), default=WatchlistCategory.ALLOWED)
    note_encrypted: Mapped[str] = mapped_column(String(1024), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    plate_hash: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    matched_category: Mapped[WatchlistCategory | None] = mapped_column(Enum(WatchlistCategory), nullable=True)
    snapshot_path: Mapped[str] = mapped_column(String(512), default="")
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    camera: Mapped["Camera"] = relationship()


class RelayEventLog(Base):
    __tablename__ = "relay_event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(32), default="detection")
    success: Mapped[bool] = mapped_column(default=False)
    message: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class ParkingState(Base):
    """Su an otoparkin icinde oldugu varsayilan araclar. Giris kamerasinda
    tespit edilince eklenir, cikis kamerasinda tespit edilince silinir.
    Satir sayisi = o an icerideki arac sayisi."""

    __tablename__ = "parking_state"

    plate_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
