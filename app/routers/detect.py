import cv2
import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.crypto import deterministic_hash, encrypt_text
from app.database import SessionLocal, get_db
from app.detection_burst import add_burst_candidate, pop_finalized_bursts
from app.models import Camera, CameraDirection, DetectionLog, ParkingState, RelayEventLog, User, WatchlistCategory
from app.notifications import maybe_send_alert
from app.outputs.relay import build_relay_driver
from app.security import get_current_user
from app.snapshots import draw_detection_boxes, save_snapshot
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


def _apply_roi(frame: np.ndarray, camera: Camera | None) -> tuple[np.ndarray, int, int]:
    """Kamerada bir tespit bolgesi (ROI) tanimliysa, kareyi o bolgeye kirpar
    (dijital yakinlastirma) - genis acili bir kamerada uzaktaki/kucuk bir
    plaka, tespit motorunun 640x640'a kucultmesiyle kaybolabiliyor; sadece
    ilgili bolgeyi tespit motoruna vermek efektif cozunurlugu artirir.
    Kirpilmis karedeki kutu koordinatlarini orijinal karedeki gercek
    konumuna geri donusturebilmek icin (x_offset, y_offset) de doner."""
    if camera is None or None in (camera.roi_x1, camera.roi_y1, camera.roi_x2, camera.roi_y2):
        return frame, 0, 0

    h, w = frame.shape[:2]
    x1 = max(0, min(w, int(camera.roi_x1 * w)))
    y1 = max(0, min(h, int(camera.roi_y1 * h)))
    x2 = max(0, min(w, int(camera.roi_x2 * w)))
    y2 = max(0, min(h, int(camera.roi_y2 * h)))
    if x2 <= x1 or y2 <= y1:
        return frame, 0, 0
    return frame[y1:y2, x1:x2], x1, y1


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


def _log_detection(
    db: Session,
    background_tasks: BackgroundTasks,
    camera: Camera | None,
    camera_id: int | None,
    plate: str,
    confidence: float,
    matched_category: WatchlistCategory | None,
    snapshot_path: str,
) -> dict:
    plate_hash = deterministic_hash(plate)
    log = DetectionLog(
        camera_id=camera_id,
        plate_encrypted=encrypt_text(plate),
        plate_hash=plate_hash,
        confidence=confidence,
        matched_category=matched_category,
        snapshot_path=snapshot_path,
    )
    db.add(log)
    db.flush()  # log.id'yi almak icin
    _update_parking_state(db, camera, plate, plate_hash)
    background_tasks.add_task(_maybe_trigger_relay, camera_id, matched_category)
    background_tasks.add_task(maybe_send_alert, plate, matched_category, camera.name if camera else "")
    return {
        "id": log.id,
        "plate": plate,
        "confidence": confidence,
        "matched_category": matched_category,
        "has_snapshot": bool(snapshot_path),
        "camera_id": camera_id,
    }


@router.post("/image")
async def detect_from_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    camera_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Bir kameraya bagli (camera_id verilmis) her tespit denemesi hemen
    kaydedilmez: ayni aracin ardisik kareleri, app/detection_burst.py'deki
    kisa sureli havuzda birikir ve arac goruntuden ayrildiginda (havuz
    "sonuclanir") COGUNLUK OYLAMASIYLA TEK bir okuma olarak kaydedilir -
    bkz. o modulun docstring'i. Kameraya bagli OLMAYAN (elle yuklenen)
    goruntuler bu birikime girmez, eskisi gibi hemen kaydedilir."""
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz gorsel")

    camera = db.get(Camera, camera_id) if camera_id is not None else None
    detect_frame, roi_x, roi_y = _apply_roi(frame, camera)
    results: list[PipelineResult] = recognize_plates(detect_frame, _get_detector(), db)

    pending: list[tuple[Camera | None, int | None, str, float, WatchlistCategory | None, str]] = []

    if results:
        if roi_x or roi_y:
            for result in results:
                result.box.x1 += roi_x
                result.box.y1 += roi_y
                result.box.x2 += roi_x
                result.box.y2 += roi_y
        annotated = draw_detection_boxes(frame, [(r.box, r.plate) for r in results])
        snapshot_path = save_snapshot(annotated)
        for result in results:
            if camera_id is not None:
                add_burst_candidate(camera_id, result.plate, result.confidence, snapshot_path, result.matched_category)
            else:
                pending.append((camera, camera_id, result.plate, result.confidence, result.matched_category, snapshot_path))

    # her denemede (arac olsun olmasin) cagrilir, boylece suresi dolmus
    # patlamalar en gec bir sonraki tespit denemesinde kaydedilir
    for finalized in pop_finalized_bursts():
        finalized_camera = db.get(Camera, finalized.camera_id)
        pending.append(
            (finalized_camera, finalized.camera_id, finalized.plate, finalized.confidence, finalized.matched_category, finalized.snapshot_path)
        )

    payload = [_log_detection(db, background_tasks, cam, cid, plate, confidence, category, snap) for cam, cid, plate, confidence, category, snap in pending]
    db.commit()

    if payload:
        by_camera: dict[int | None, list[dict]] = {}
        for entry in payload:
            by_camera.setdefault(entry["camera_id"], []).append(entry)
        for cid, entries in by_camera.items():
            await broadcast_detection({"camera_id": cid, "detections": entries})

    return payload
