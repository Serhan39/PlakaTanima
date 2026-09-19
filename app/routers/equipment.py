from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_text, deterministic_hash, encrypt_text
from app.database import get_db
from app.models import (
    CameraDirection,
    EquipmentCrossingLog,
    EquipmentGate,
    EquipmentState,
    EquipmentZone,
    User,
    UserRole,
)
from app.schemas import (
    EquipmentCrossingRead,
    EquipmentCrossingSubmit,
    EquipmentGateCreate,
    EquipmentGateLineUpdate,
    EquipmentGateRead,
    EquipmentStatusRead,
    EquipmentTimeReportEntry,
    EquipmentZoneCreate,
    EquipmentZoneDuration,
    EquipmentZoneRead,
    FeatureFlag,
)
from app.security import get_current_user, require_roles
from app.settings_store import get_setting, set_setting
from app.vision.pipeline import build_default_detector, recognize_equipment_codes
from app.websocket_manager import broadcast_equipment_event

router = APIRouter(prefix="/api/equipment", tags=["equipment"])

_FEATURE_KEY = "equipment_tracking_enabled"
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = build_default_detector()
    return _detector


# --- Ozellik acma/kapama -----------------------------------------------

@router.get("/feature-status", response_model=FeatureFlag)
def feature_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    enabled = get_setting(db, _FEATURE_KEY, "false") == "true"
    return FeatureFlag(enabled=enabled)


@router.put("/feature-status", response_model=FeatureFlag, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def set_feature_status(payload: FeatureFlag, db: Session = Depends(get_db)):
    set_setting(db, _FEATURE_KEY, "true" if payload.enabled else "false")
    return payload


# --- Alanlar (zones) -----------------------------------------------------

@router.get("/zones", response_model=list[EquipmentZoneRead])
def list_zones(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(EquipmentZone).order_by(EquipmentZone.id).all()


@router.post("/zones", response_model=EquipmentZoneRead, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create_zone(payload: EquipmentZoneCreate, db: Session = Depends(get_db)):
    if db.query(EquipmentZone).filter(EquipmentZone.name == payload.name).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu isimde bir alan zaten var")
    zone = EquipmentZone(name=payload.name)
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


@router.delete("/zones/{zone_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def delete_zone(zone_id: int, db: Session = Depends(get_db)):
    zone = db.get(EquipmentZone, zone_id)
    if not zone:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alan bulunamadi")
    if db.query(EquipmentGate).filter(EquipmentGate.zone_id == zone_id).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu alana bagli kapilar var, once onlari silin")
    db.delete(zone)
    db.commit()


# --- Kapilar (gates) -------------------------------------------------------

@router.get("/gates", response_model=list[EquipmentGateRead])
def list_gates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(EquipmentGate).order_by(EquipmentGate.id).all()


@router.post("/gates", response_model=EquipmentGateRead, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create_gate(payload: EquipmentGateCreate, db: Session = Depends(get_db)):
    if not db.get(EquipmentZone, payload.zone_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz alan")
    gate = EquipmentGate(**payload.model_dump())
    db.add(gate)
    db.commit()
    db.refresh(gate)
    return gate


@router.delete("/gates/{gate_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def delete_gate(gate_id: int, db: Session = Depends(get_db)):
    gate = db.get(EquipmentGate, gate_id)
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kapi bulunamadi")
    db.delete(gate)
    db.commit()


@router.put("/gates/{gate_id}/line", response_model=EquipmentGateRead, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def update_gate_line(gate_id: int, payload: EquipmentGateLineUpdate, db: Session = Depends(get_db)):
    gate = db.get(EquipmentGate, gate_id)
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kapi bulunamadi")
    gate.line_x1 = payload.line_x1
    gate.line_y1 = payload.line_y1
    gate.line_x2 = payload.line_x2
    gate.line_y2 = payload.line_y2
    gate.inside_x = payload.inside_x
    gate.inside_y = payload.inside_y
    db.commit()
    db.refresh(gate)
    return gate


@router.get(
    "/gates/{gate_id}/preview",
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))],
)
def gate_preview(gate_id: int, db: Session = Depends(get_db)):
    """Kapinin RTSP adresinden tek bir kare cekip JPEG olarak dondurur;
    panelde cizgi cizme aracinin arka plan goruntusu icin kullanilir."""
    gate = db.get(EquipmentGate, gate_id)
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kapi bulunamadi")
    if not gate.rtsp_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kapi icin RTSP adresi tanimli degil")

    capture = cv2.VideoCapture(gate.rtsp_url)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Kameradan goruntu alinamadi")

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Goruntu kodlanamadi")
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


# --- Durum ve kayitlar ------------------------------------------------------

@router.get("/status", response_model=list[EquipmentStatusRead])
def status_list(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(EquipmentState).order_by(EquipmentState.updated_at.desc()).all()
    zones = {z.id: z.name for z in db.query(EquipmentZone).all()}
    return [
        EquipmentStatusRead(
            plate=decrypt_text(row.plate_encrypted),
            zone_id=row.zone_id,
            zone_name=zones.get(row.zone_id, "Disarida") if row.zone_id else "Disarida",
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def _default_range(date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime]:
    """SQLite, DateTime(timezone=True) kolonlarindaki saat dilimi bilgisini
    saklamiyor: veritabanindan okunan created_at degerleri her zaman naive
    (tzinfo'suz) gelir. Varsayilan `end` (datetime.now(timezone.utc)) ise
    aware'dir; ikisini karsilastirmak/cikarmak TypeError'a ya da sessizce
    yanlis SQL filtrelemeye yol acar. Bu yuzden burada her iki ucta da
    tzinfo'yu atip, tum hesaplamayi tutarli sekilde naive-UTC uzerinden
    yapiyoruz."""
    end = (date_to or datetime.now(timezone.utc)).replace(tzinfo=None)
    start = (date_from.replace(tzinfo=None) if date_from else end - timedelta(days=7))
    return start, end


@router.get("/logs", response_model=list[EquipmentCrossingRead])
def crossing_logs(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    zone_id: int | None = None,
    gate_id: int | None = None,
    plate_query: str | None = None,
    limit: int = 200,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start, end = _default_range(date_from, date_to)
    query = db.query(EquipmentCrossingLog).filter(
        EquipmentCrossingLog.created_at >= start, EquipmentCrossingLog.created_at < end
    )
    if zone_id is not None:
        query = query.filter(EquipmentCrossingLog.zone_id == zone_id)
    if gate_id is not None:
        query = query.filter(EquipmentCrossingLog.gate_id == gate_id)
    rows = query.order_by(EquipmentCrossingLog.created_at.desc()).limit(min(limit, 500)).all()

    zones = {z.id: z.name for z in db.query(EquipmentZone).all()}
    gates = {g.id: g.name for g in db.query(EquipmentGate).all()}

    needle = (plate_query or "").strip().upper().replace(" ", "")
    results = []
    for row in rows:
        plate = decrypt_text(row.plate_encrypted)
        if needle and needle not in plate.replace(" ", "").upper():
            continue
        results.append(
            EquipmentCrossingRead(
                plate=plate,
                gate_id=row.gate_id,
                gate_name=gates.get(row.gate_id, "?"),
                zone_id=row.zone_id,
                zone_name=zones.get(row.zone_id, "?"),
                direction=row.direction,
                confidence=row.confidence,
                created_at=row.created_at,
            )
        )
    return results


@router.get("/time-report", response_model=list[EquipmentTimeReportEntry])
def time_report(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Her is makinesinin secilen tarih araliginda hangi alanda (veya
    disarida) ne kadar sure gecirdigini hesaplar. Gecis kayitlari arasindaki
    zaman farklarini, aralaigin baslangicindaki durumdan itibaren zincirleme
    olarak ilgili alana/disari'ya yazarak bulur."""
    start, end = _default_range(date_from, date_to)
    zones = {z.id: z.name for z in db.query(EquipmentZone).all()}

    plate_hashes = [row[0] for row in db.query(EquipmentCrossingLog.plate_hash).distinct().all()]

    entries: list[EquipmentTimeReportEntry] = []
    for plate_hash in plate_hashes:
        prior = (
            db.query(EquipmentCrossingLog)
            .filter(EquipmentCrossingLog.plate_hash == plate_hash, EquipmentCrossingLog.created_at < start)
            .order_by(EquipmentCrossingLog.created_at.desc())
            .first()
        )
        events = (
            db.query(EquipmentCrossingLog)
            .filter(
                EquipmentCrossingLog.plate_hash == plate_hash,
                EquipmentCrossingLog.created_at >= start,
                EquipmentCrossingLog.created_at < end,
            )
            .order_by(EquipmentCrossingLog.created_at.asc())
            .all()
        )
        if not prior and not events:
            continue

        current_zone_id = prior.zone_id if prior and prior.direction == CameraDirection.ENTRY else None
        plate_encrypted = prior.plate_encrypted if prior else events[0].plate_encrypted

        durations: dict[int | None, float] = {}
        cursor = start
        for event in events:
            elapsed = max((event.created_at - cursor).total_seconds(), 0)
            durations[current_zone_id] = durations.get(current_zone_id, 0.0) + elapsed
            current_zone_id = event.zone_id if event.direction == CameraDirection.ENTRY else None
            cursor = event.created_at

        durations[current_zone_id] = durations.get(current_zone_id, 0.0) + max((end - cursor).total_seconds(), 0)

        breakdown = [
            EquipmentZoneDuration(
                zone_id=zid,
                zone_name=zones.get(zid, "Disarida") if zid else "Disarida",
                duration_seconds=round(secs),
            )
            for zid, secs in sorted(durations.items(), key=lambda kv: -kv[1])
            if round(secs) > 0
        ]
        entries.append(
            EquipmentTimeReportEntry(
                plate=decrypt_text(plate_encrypted),
                breakdown=breakdown,
                total_seconds=round(sum(durations.values())),
            )
        )

    entries.sort(key=lambda e: e.plate)
    return entries


# --- Tespit ------------------------------------------------------------------

def _is_debounced(db: Session, gate_id: int, plate_hash: str) -> bool:
    window = get_settings().equipment_crossing_debounce_seconds
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=window)
    existing = (
        db.query(EquipmentCrossingLog)
        .filter(
            EquipmentCrossingLog.gate_id == gate_id,
            EquipmentCrossingLog.plate_hash == plate_hash,
            EquipmentCrossingLog.created_at >= cutoff,
        )
        .first()
    )
    return existing is not None


def apply_crossing(
    db: Session,
    gate: EquipmentGate,
    code: str,
    confidence: float,
    direction: CameraDirection | None = None,
) -> dict | None:
    """Bir gecis okumasini isler: debounce icindeyse None doner (yoksayilir),
    degilse EquipmentCrossingLog + EquipmentState'i gunceller ve yayinlanacak
    olay mesajini uretip dondurur. Router'dan ayri, dogrudan test edilebilir.

    `direction` verilmezse gate.direction kullanilir (eski tek-kare modu /
    sabit yonlu kapilar icin). Cizgi takibi yapan worker, her gecis icin
    gercek yonu (icerisi referans noktasina gore hesaplanmis) acikca
    gonderir - boylece ayni kapi hem giren hem cikan araci ayirt edebilir."""
    effective_direction = direction or gate.direction

    plate_hash = deterministic_hash(code)
    if _is_debounced(db, gate.id, plate_hash):
        return None

    db.add(
        EquipmentCrossingLog(
            gate_id=gate.id,
            plate_encrypted=encrypt_text(code),
            plate_hash=plate_hash,
            direction=effective_direction,
            zone_id=gate.zone_id,
            confidence=confidence,
        )
    )

    new_zone_id = gate.zone_id if effective_direction == CameraDirection.ENTRY else None
    state = db.get(EquipmentState, plate_hash)
    if state:
        state.zone_id = new_zone_id
        state.updated_at = datetime.now(timezone.utc)
    else:
        db.add(EquipmentState(plate_hash=plate_hash, plate_encrypted=encrypt_text(code), zone_id=new_zone_id))

    if effective_direction == CameraDirection.EXIT:
        message = f"{code} plakali arac disarida"
    else:
        message = f"{code} plakali arac {gate.zone.name} alaninda"

    return {
        "plate": code,
        "gate_id": gate.id,
        "zone_id": gate.zone_id,
        "zone_name": gate.zone.name,
        "direction": effective_direction.value,
        "message": message,
        "confidence": confidence,
    }


@router.post("/detect/image")
async def detect_equipment(
    gate_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    gate = db.get(EquipmentGate, gate_id)
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kapi bulunamadi")

    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz gorsel")

    settings = get_settings()
    detections = recognize_equipment_codes(frame, _get_detector(), min_length=settings.equipment_min_code_length)

    events = []
    for detection in detections:
        event = apply_crossing(db, gate, detection.code, detection.confidence)
        if event:
            events.append(event)

    db.commit()

    if events:
        await broadcast_equipment_event({"gate_id": gate.id, "events": events})
    return events


@router.post("/crossings")
async def submit_crossing(
    payload: EquipmentCrossingSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Cizgi takibi yapan worker'in (app/equipment_gate_worker.py), bir
    aracin sanal cizgiyi FIILEN gectigini tespit ettiginde cagirdigi uc.
    /detect/image'in aksine burada tespit tekrar yapilmaz - worker zaten
    kendi takip dongusunde en iyi OCR okumasini belirlemistir, burada
    sadece debounce + durum guncelleme + yayinlama yapilir."""
    gate = db.get(EquipmentGate, payload.gate_id)
    if not gate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kapi bulunamadi")

    event = apply_crossing(db, gate, payload.code, payload.confidence, direction=payload.direction)
    db.commit()

    if event:
        await broadcast_equipment_event({"gate_id": gate.id, "events": [event]})
        return event
    return {"debounced": True}
