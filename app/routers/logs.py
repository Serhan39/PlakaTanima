from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.crypto import decrypt_text
from app.database import get_db
from app.models import DetectionLog, User
from app.schemas import DetectionResult
from app.security import get_current_user

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("", response_model=list[DetectionResult])
def list_logs(limit: int = 100, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    logs = db.query(DetectionLog).order_by(DetectionLog.detected_at.desc()).limit(min(limit, 500)).all()
    return [
        DetectionResult(
            id=log.id,
            plate=decrypt_text(log.plate_encrypted),
            confidence=log.confidence,
            matched_category=log.matched_category,
            detected_at=log.detected_at,
            camera_id=log.camera_id,
            has_snapshot=bool(log.snapshot_path),
        )
        for log in logs
    ]


@router.get("/{log_id}/snapshot")
def get_snapshot(log_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    log = db.get(DetectionLog, log_id)
    if not log or not log.snapshot_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fotograf bulunamadi")

    path = Path(log.snapshot_path)
    if not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fotograf dosyasi bulunamadi")

    return FileResponse(path, media_type="image/jpeg")
