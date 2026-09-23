import enum
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite, DateTime(timezone=True) ile bile timezone bilgisini
    KORUMAZ - yazarken UTC olarak kaydedilen bir deger, okunurken tzinfo'su
    olmayan (naive) bir datetime olarak geri doner. Bu, API yanitlarinda
    tarihin "UTC oldugu belirtilmeden" serilize edilmesine (orn.
    "2026-09-23T09:47:50", sonunda 'Z'/ofset olmadan) yol aciyordu -
    tarayici bunu YEREL saatmis gibi yorumlayip HIC donusturmuyordu, bu
    yuzden kullaniciya log saatleri kamera saatinden (Turkiye, UTC+3)
    3 saat geri gorunuyordu ("saat yanlis" sikayeti). Okurken tzinfo=utc
    ekleyerek, deger DB'de her zaman UTC olarak yazildigi icin, dogru
    sekilde UTC oldugunu garanti eder - boylece tarayici kendi yerel
    saatine dogru cevirir."""

    impl = DateTime
    cache_ok = True

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)

    # Role'den bagimsiz, kullaniciya ozel bir yetki: rolu "izleyici" olsa
    # bile, bu isaretliyse Is Makinasi Takip ozelligini acip kapatabilir.
    can_manage_equipment: Mapped[bool] = mapped_column(default=False)


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
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)

    relay_type: Mapped[RelayType] = mapped_column(Enum(RelayType), default=RelayType.NONE)
    relay_target: Mapped[str] = mapped_column(String(255), default="")
    relay_command: Mapped[str] = mapped_column(String(255), default="")
    relay_pulse_seconds: Mapped[float] = mapped_column(Float, default=3.0)
    open_categories: Mapped[str] = mapped_column(String(255), default="allowed,staff")
    direction: Mapped[CameraDirection] = mapped_column(Enum(CameraDirection), default=CameraDirection.NONE)

    # Tespit bolgesi (ROI, normalize 0-1 koordinatlar): genis acili kameralarda
    # arac/plaka goruntude kucuk kalip tespit motoruna (640x640) kucultulunce
    # kaybolabiliyor. Tanimliysa, tespit ONCESI kare bu bolgeye kirpilip
    # (dijital yakinlastirma) tespit motoruna oyle verilir - boylece ayni
    # kamera degistirilmeden efektif cozunurluk artar. Bos ise (None) tum
    # kare kullanilir (eski davranis, geriye donuk uyumlu).
    roi_x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    roi_y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    roi_x2: Mapped[float | None] = mapped_column(Float, nullable=True)
    roi_y2: Mapped[float | None] = mapped_column(Float, nullable=True)


class WatchlistEntry(Base):
    __tablename__ = "watchlist_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    plate_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    category: Mapped[WatchlistCategory] = mapped_column(Enum(WatchlistCategory), default=WatchlistCategory.ALLOWED)
    note_encrypted: Mapped[str] = mapped_column(String(1024), default="")
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)


class DetectionLog(Base):
    __tablename__ = "detection_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    plate_hash: Mapped[str] = mapped_column(String(64), index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    matched_category: Mapped[WatchlistCategory | None] = mapped_column(Enum(WatchlistCategory), nullable=True)
    snapshot_path: Mapped[str] = mapped_column(String(512), default="")
    detected_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow, index=True)

    camera: Mapped["Camera"] = relationship()


class RelayEventLog(Base):
    __tablename__ = "relay_event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(32), default="detection")
    success: Mapped[bool] = mapped_column(default=False)
    message: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow, index=True)


class ParkingState(Base):
    """Su an otoparkin icinde oldugu varsayilan araclar. Giris kamerasinda
    tespit edilince eklenir, cikis kamerasinda tespit edilince silinir.
    Satir sayisi = o an icerideki arac sayisi."""

    __tablename__ = "parking_state"

    plate_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    camera_id: Mapped[int | None] = mapped_column(ForeignKey("cameras.id"), nullable=True)
    entered_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))


class EquipmentZone(Base):
    """Fabrika icinde is makinelerinin bulunabilecegi adlandirilmis alanlar
    (orn. 'A Alani', 'B Alani')."""

    __tablename__ = "equipment_zones"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)


class EquipmentGate(Base):
    """Bir alanin girisi/cikisi olan kapiya takili kamera. direction=entry
    ise bu kapidan gecen makine zone_id alanina girmis, direction=exit ise
    zone_id alanindan cikip disariya gecmis sayilir."""

    __tablename__ = "equipment_gates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    rtsp_url: Mapped[str] = mapped_column(String(512), default="")
    zone_id: Mapped[int] = mapped_column(ForeignKey("equipment_zones.id"))
    # direction: tabloda gosterim ve cizgi tanimlanmamis/eski tek-kare modu
    # (/detect/image) icin varsayilan/yedek yon. Cizgi takibi (worker) aktif
    # oldugunda gercek yon, her gecis icin ayri ayri asagidaki cizgi +
    # icerisi referans noktasindan dinamik hesaplanir (bkz. inside_x/y).
    direction: Mapped[CameraDirection] = mapped_column(Enum(CameraDirection))
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)

    # Kameranin genis bir alani gordugu kurulumlarda, aracin sadece
    # goruntude "bulunmasini" degil, bu sanal cizgiyi fiilen gecmesini
    # tespit etmek icin kullanilan iki uc nokta (goruntu genisligi/
    # yuksekligine gore normalize edilmis, 0-1 araliginda).
    line_x1: Mapped[float] = mapped_column(Float, default=0.1)
    line_y1: Mapped[float] = mapped_column(Float, default=0.5)
    line_x2: Mapped[float] = mapped_column(Float, default=0.9)
    line_y2: Mapped[float] = mapped_column(Float, default=0.5)

    # Cizginin hangi tarafinin "icerisi" (zone_id alani) oldugunu isaret
    # eden referans nokta; bir aracin gectikten sonraki tarafi bu noktayla
    # ayni tarafta ise GIRIS, degilse CIKIS sayilir (bkz. app/vision/tracker.py).
    inside_x: Mapped[float] = mapped_column(Float, default=0.5)
    inside_y: Mapped[float] = mapped_column(Float, default=0.1)

    zone: Mapped["EquipmentZone"] = relationship()


class EquipmentState(Base):
    """Her is makinesinin (plakasina gore) su an hangi alanda oldugu.
    zone_id NULL ise makine hicbir alanda degil (disarida) demektir."""

    __tablename__ = "equipment_state"

    plate_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    zone_id: Mapped[int | None] = mapped_column(ForeignKey("equipment_zones.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow)


class EquipmentCrossingLog(Base):
    __tablename__ = "equipment_crossing_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    gate_id: Mapped[int] = mapped_column(ForeignKey("equipment_gates.id"))
    plate_encrypted: Mapped[str] = mapped_column(String(512))
    plate_hash: Mapped[str] = mapped_column(String(64), index=True)
    direction: Mapped[CameraDirection] = mapped_column(Enum(CameraDirection))
    zone_id: Mapped[int] = mapped_column(ForeignKey("equipment_zones.id"))
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(16), default="camera")  # "camera" ya da "manual" (elle duzeltme)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(timezone=True), default=_utcnow, index=True)
