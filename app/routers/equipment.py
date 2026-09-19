from datetime import datetime, timedelta, timezone

import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
    EquipmentGateCreate,
    EquipmentGateRead,
    EquipmentStatusRead,
    EquipmentZoneCreate,
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


@router.get("/logs", response_model=list[EquipmentCrossingRead])
def crossing_logs(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    rows = db.query(EquipmentCrossingLog).order_by(EquipmentCrossingLog.created_at.desc()).limit(min(limit, 500)).all()
    return [
        EquipmentCrossingRead(
            plate=decrypt_text(row.plate_encrypted),
            gate_id=row.gate_id,
            zone_id=row.zone_id,
            direction=row.direction,
            confidence=row.confidence,
            created_at=row.created_at,
        )
        for row in rows
    ]


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


def apply_crossing(db: Session, gate: EquipmentGate, code: str, confidence: float) -> dict | None:
    """Bir gecis okumasini isler: debounce icindeyse None doner (yoksayilir),
    degilse EquipmentCrossingLog + EquipmentState'i gunceller ve yayinlanacak
    olay mesajini uretip dondurur. Router'dan ayri, dogrudan test edilebilir."""
    plate_hash = deterministic_hash(code)
    if _is_debounced(db, gate.id, plate_hash):
        return None

    db.add(
        EquipmentCrossingLog(
            gate_id=gate.id,
            plate_encrypted=encrypt_text(code),
            plate_hash=plate_hash,
            direction=gate.direction,
            zone_id=gate.zone_id,
            confidence=confidence,
        )
    )

    new_zone_id = gate.zone_id if gate.direction == CameraDirection.ENTRY else None
    state = db.get(EquipmentState, plate_hash)
    if state:
        state.zone_id = new_zone_id
        state.updated_at = datetime.now(timezone.utc)
    else:
        db.add(EquipmentState(plate_hash=plate_hash, plate_encrypted=encrypt_text(code), zone_id=new_zone_id))

    if gate.direction == CameraDirection.EXIT:
        message = f"{code} plakali arac disarida"
    else:
        message = f"{code} plakali arac {gate.zone.name} alaninda"

    return {
        "plate": code,
        "gate_id": gate.id,
        "zone_id": gate.zone_id,
        "zone_name": gate.zone.name,
        "direction": gate.direction.value,
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
