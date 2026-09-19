import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.crypto import deterministic_hash, encrypt_text
from app.database import SessionLocal, get_db
from app.models import Camera, CameraDirection, DetectionLog, ParkingState, RelayEventLog, User, WatchlistCategory
from app.notifications import maybe_send_alert
from app.outputs.relay import build_relay_driver
from app.security import get_current_user
from app.vision.pipeline import PipelineResult, build_default_detector, recognize_plates
from app.websocket_manager import broadcast_detection

router = APIRouter(prefix="/api/detect", tags=["detect"])
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = build_default_detector()
    return _detector


def _maybe_trigger_relay(camera_id: int | None, category: WatchlistCategory | None) -> None:
    if camera_id is None or category is None:
        return
    db = SessionLocal()
    try:
        camera = db.get(Camera, camera_id)
        if not camera:
            return
        open_categories = {c.strip() for c in camera.open_categories.split(",") if c.strip()}
        if category.value not in open_categories:
            return
        driver = build_relay_driver(camera)
        success, message = driver.trigger_open(camera.relay_pulse_seconds)
        db.add(RelayEventLog(camera_id=camera.id, triggered_by="detection", success=success, message=message))
        db.commit()
    finally:
        db.close()


def _update_parking_state(db: Session, camera: Camera | None, plate: str, plate_hash: str) -> None:
    if camera is None or camera.direction == CameraDirection.NONE:
        return
    if camera.direction == CameraDirection.ENTRY:
        if not db.get(ParkingState, plate_hash):
            db.add(ParkingState(plate_hash=plate_hash, plate_encrypted=encrypt_text(plate), camera_id=camera.id))
    elif camera.direction == CameraDirection.EXIT:
        existing = db.get(ParkingState, plate_hash)
        if existing:
            db.delete(existing)


@router.post("/image")
async def detect_from_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    camera_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz gorsel")

    camera = db.get(Camera, camera_id) if camera_id is not None else None
    results: list[PipelineResult] = recognize_plates(frame, _get_detector(), db)
    for result in results:
        log = DetectionLog(
            camera_id=camera_id,
            plate_encrypted=encrypt_text(result.plate),
            plate_hash=deterministic_hash(result.plate),
            confidence=result.confidence,
            matched_category=result.matched_category,
        )
        db.add(log)
        _update_parking_state(db, camera, result.plate, deterministic_hash(result.plate))
        background_tasks.add_task(_maybe_trigger_relay, camera_id, result.matched_category)
        background_tasks.add_task(maybe_send_alert, result.plate, result.matched_category, camera.name if camera else "")
    db.commit()

    payload = [r.__dict__ for r in results]
    await broadcast_detection({"camera_id": camera_id, "detections": payload})
    return payload
