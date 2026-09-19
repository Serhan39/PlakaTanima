import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.crypto import decrypt_text
from app.database import get_db
from app.models import Camera, DetectionLog, User, WatchlistCategory
from app.notifications import send_daily_report
from app.schemas import DetectionResult, ReportSummary
from app.security import get_current_user

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _default_range(date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime]:
    """SQLite, DateTime(timezone=True) kolonlarindaki saat dilimi bilgisini
    saklamiyor: veritabanindan okunan detected_at degerleri her zaman naive
    (tzinfo'suz) gelir. Varsayilan `end` (datetime.now(timezone.utc)) ise
    aware'dir; bu ikisini SQL filtresinde birlikte kullanmak sessizce yanlis
    sonuc verebilir. Tutarlilik icin her iki ucta da tzinfo'yu atiyoruz."""
    end = (date_to or datetime.now(timezone.utc)).replace(tzinfo=None)
    start = (date_from.replace(tzinfo=None) if date_from else end - timedelta(days=7))
    return start, end


def _filtered_query(
    db: Session,
    date_from: datetime,
    date_to: datetime,
    camera_id: int | None,
    category: WatchlistCategory | None,
):
    query = db.query(DetectionLog).filter(DetectionLog.detected_at >= date_from, DetectionLog.detected_at < date_to)
    if camera_id is not None:
        query = query.filter(DetectionLog.camera_id == camera_id)
    if category is not None:
        query = query.filter(DetectionLog.matched_category == category)
    return query


@router.get("/summary", response_model=ReportSummary)
def summary(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_id: int | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start, end = _default_range(date_from, date_to)
    base = _filtered_query(db, start, end, camera_id, None)
    total = base.count()

    category_query = db.query(DetectionLog.matched_category, func.count(DetectionLog.id)).filter(
        DetectionLog.detected_at >= start, DetectionLog.detected_at < end
    )
    if camera_id is not None:
        category_query = category_query.filter(DetectionLog.camera_id == camera_id)
    by_category_rows = category_query.group_by(DetectionLog.matched_category).all()
    by_category = {(cat.value if cat else "kayitsiz"): count for cat, count in by_category_rows}

    by_camera_rows = (
        db.query(Camera.id, Camera.name, func.count(DetectionLog.id))
        .join(DetectionLog, DetectionLog.camera_id == Camera.id)
        .filter(DetectionLog.detected_at >= start, DetectionLog.detected_at < end)
        .group_by(Camera.id, Camera.name)
        .all()
    )
    by_camera = [{"camera_id": cid, "camera_name": name, "count": count} for cid, name, count in by_camera_rows]

    hour_query = db.query(func.strftime("%H", DetectionLog.detected_at), func.count(DetectionLog.id)).filter(
        DetectionLog.detected_at >= start, DetectionLog.detected_at < end
    )
    if camera_id is not None:
        hour_query = hour_query.filter(DetectionLog.camera_id == camera_id)
    by_hour_rows = hour_query.group_by(func.strftime("%H", DetectionLog.detected_at)).all()
    by_hour = [{"hour": int(hour), "count": count} for hour, count in by_hour_rows]

    return ReportSummary(date_from=start, date_to=end, total=total, by_category=by_category, by_camera=by_camera, by_hour=by_hour)


@router.get("/logs", response_model=list[DetectionResult])
def logs(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_id: int | None = None,
    category: WatchlistCategory | None = None,
    plate_query: str | None = Query(default=None, description="Plaka icinde gecen metin"),
    limit: int = 500,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start, end = _default_range(date_from, date_to)
    rows = _filtered_query(db, start, end, camera_id, category).order_by(DetectionLog.detected_at.desc()).limit(min(limit, 2000)).all()

    results = []
    needle = (plate_query or "").strip().upper().replace(" ", "")
    for row in rows:
        plate = decrypt_text(row.plate_encrypted)
        if needle and needle not in plate.replace(" ", ""):
            continue
        results.append(
            DetectionResult(
                id=row.id,
                plate=plate,
                confidence=row.confidence,
                matched_category=row.matched_category,
                detected_at=row.detected_at,
                camera_id=row.camera_id,
                has_snapshot=bool(row.snapshot_path),
            )
        )
    return results


@router.get("/export.csv")
def export_csv(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    camera_id: int | None = None,
    category: WatchlistCategory | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    start, end = _default_range(date_from, date_to)
    rows = _filtered_query(db, start, end, camera_id, category).order_by(DetectionLog.detected_at.desc()).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["Tarih", "Plaka", "Kamera ID", "Kategori", "Guven"])
    for row in rows:
        writer.writerow(
            [
                row.detected_at.isoformat(),
                decrypt_text(row.plate_encrypted),
                row.camera_id or "",
                row.matched_category.value if row.matched_category else "",
                row.confidence,
            ]
        )
    buffer.seek(0)
    filename = f"sertek-alpr-rapor-{start.date()}_{end.date()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/send-daily")
def send_daily_now(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    sent = send_daily_report(db)
    return {"sent": sent}
