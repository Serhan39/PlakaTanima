"""E-posta bildirimleri: onemli olay (aranan/kara liste) aninda uyarisi ve
gunluk ozet rapor. SMTP yapilandirilmamissa (smtp_host bos) sessizce atlanir;
bu sayede e-posta ozelligi olmadan da sistem sorunsuz calisir."""

import logging
import smtplib
from datetime import date, datetime, time, timedelta, timezone
from email.mime.text import MIMEText

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crypto import decrypt_text
from app.models import Camera, DetectionLog, WatchlistCategory

logger = logging.getLogger("sertek_alpr.notifications")

_CATEGORY_LABELS = {
    WatchlistCategory.ALLOWED: "Izinli",
    WatchlistCategory.STAFF: "Personel",
    WatchlistCategory.WANTED: "Aranan",
    WatchlistCategory.BLACKLIST: "Kara Liste",
}


def _recipients(raw: str) -> list[str]:
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def send_email(subject: str, body: str, to: list[str]) -> bool:
    settings = get_settings()
    if not settings.smtp_host or not to:
        logger.info("SMTP yapilandirilmamis veya alici yok, e-posta gonderilmedi: %s", subject)
        return False

    message = MIMEText(body, "plain", "utf-8")
    message["Subject"] = subject
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = ", ".join(to)

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            if settings.smtp_use_tls:
                server.starttls()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(message["From"], to, message.as_string())
        return True
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("E-posta gonderilemedi: %s", exc)
        return False


def maybe_send_alert(plate: str, category: WatchlistCategory | None, camera_name: str) -> bool:
    settings = get_settings()
    alert_categories = {c.strip() for c in settings.alert_categories.split(",") if c.strip()}
    if not category or category.value not in alert_categories:
        return False

    label = _CATEGORY_LABELS.get(category, category.value)
    subject = f"[Sertek ALPR] {label} plaka tespit edildi: {plate}"
    body = (
        f"Plaka: {plate}\n"
        f"Kategori: {label}\n"
        f"Kamera: {camera_name or 'Bilinmiyor'}\n"
        f"Zaman: {datetime.now(timezone.utc).isoformat()}\n"
    )
    return send_email(subject, body, _recipients(settings.alert_to))


def build_daily_report(db: Session, for_date: date | None = None) -> tuple[str, str]:
    # Gun sinirlari UTC'ye gore hesaplanir (DetectionLog.detected_at,
    # app/models.py::UTCDateTime sayesinde her zaman aware-UTC'dir).
    for_date = for_date or date.today()
    start = datetime.combine(for_date, time.min, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    query = db.query(DetectionLog).filter(DetectionLog.detected_at >= start, DetectionLog.detected_at < end)
    total = query.count()

    by_category = dict(
        db.query(DetectionLog.matched_category, func.count(DetectionLog.id))
        .filter(DetectionLog.detected_at >= start, DetectionLog.detected_at < end)
        .group_by(DetectionLog.matched_category)
        .all()
    )

    by_camera = (
        db.query(Camera.name, func.count(DetectionLog.id))
        .join(DetectionLog, DetectionLog.camera_id == Camera.id)
        .filter(DetectionLog.detected_at >= start, DetectionLog.detected_at < end)
        .group_by(Camera.name)
        .all()
    )

    alert_rows = query.filter(DetectionLog.matched_category.in_([WatchlistCategory.WANTED, WatchlistCategory.BLACKLIST])).all()

    lines = [
        f"Sertek ALPR Gunluk Rapor - {for_date.isoformat()}",
        "=" * 40,
        f"Toplam tespit: {total}",
        "",
        "Kategoriye gore dagilim:",
    ]
    for category in WatchlistCategory:
        count = by_category.get(category, 0)
        lines.append(f"  {_CATEGORY_LABELS[category]}: {count}")
    lines.append(f"  Kayitsiz (eslesmeyen): {by_category.get(None, 0)}")

    lines.append("")
    lines.append("Kameraya gore dagilim:")
    if by_camera:
        for camera_name, count in by_camera:
            lines.append(f"  {camera_name}: {count}")
    else:
        lines.append("  (kayit yok)")

    lines.append("")
    lines.append(f"Onemli olaylar (Aranan/Kara Liste) - {len(alert_rows)} adet:")
    if alert_rows:
        for row in alert_rows:
            plate = decrypt_text(row.plate_encrypted)
            lines.append(f"  {row.detected_at.strftime('%H:%M')} - {plate} ({_CATEGORY_LABELS[row.matched_category]})")
    else:
        lines.append("  (yok)")

    subject = f"[Sertek ALPR] Gunluk Rapor - {for_date.isoformat()} ({total} tespit)"
    return subject, "\n".join(lines)


def send_daily_report(db: Session, for_date: date | None = None) -> bool:
    settings = get_settings()
    subject, body = build_daily_report(db, for_date)
    return send_email(subject, body, _recipients(settings.daily_report_to))
