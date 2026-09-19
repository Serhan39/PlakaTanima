from fastapi import APIRouter, Depends
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
            plate=decrypt_text(log.plate_encrypted),
            confidence=log.confidence,
            matched_category=log.matched_category,
            detected_at=log.detected_at,
            camera_id=log.camera_id,
        )
        for log in logs
    ]
