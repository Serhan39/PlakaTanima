import cv2
import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.crypto import deterministic_hash, encrypt_text
from app.database import get_db
from app.models import DetectionLog, User
from app.security import get_current_user
from app.vision.pipeline import build_default_detector, recognize_plates
from app.websocket_manager import broadcast_detection

router = APIRouter(prefix="/api/detect", tags=["detect"])
_detector = None


def _get_detector():
    global _detector
    if _detector is None:
        _detector = build_default_detector()
    return _detector


@router.post("/image")
async def detect_from_image(
    file: UploadFile = File(...),
    camera_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = await file.read()
    frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecersiz gorsel")

    results = recognize_plates(frame, _get_detector(), db)
    for result in results:
        log = DetectionLog(
            camera_id=camera_id,
            plate_encrypted=encrypt_text(result.plate),
            plate_hash=deterministic_hash(result.plate),
            confidence=result.confidence,
            matched_category=result.matched_category,
        )
        db.add(log)
    db.commit()

    payload = [r.__dict__ for r in results]
    await broadcast_detection({"camera_id": camera_id, "detections": payload})
    return payload
