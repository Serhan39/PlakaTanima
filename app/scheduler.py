"""Gunluk rapor e-postasini, ayri bir isletim sistemi zamanlayicisi (cron/Task
Scheduler) kurulumu gerektirmeden, uygulama icinde otomatik gonderen basit
arka plan dongusu. Her dakika kontrol eder; DAILY_REPORT_HOUR saatine
gelindiginde ve o gun icin henuz gonderilmediyse raporu yollar."""

import asyncio
import logging
from datetime import date, datetime
from pathlib import Path

from app.config import get_settings
from app.database import SessionLocal
from app.notifications import send_daily_report

logger = logging.getLogger("sertek_alpr.scheduler")
_STATE_FILE = Path("data/daily_report_last_sent.txt")


def _already_sent_today() -> bool:
    if not _STATE_FILE.exists():
        return False
    return _STATE_FILE.read_text().strip() == date.today().isoformat()


def _mark_sent_today() -> None:
    _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STATE_FILE.write_text(date.today().isoformat())


async def daily_report_loop(poll_seconds: float = 60.0) -> None:
    while True:
        settings = get_settings()
        if settings.daily_report_to:
            now = datetime.now()
            if now.hour == settings.daily_report_hour and not _already_sent_today():
                db = SessionLocal()
                try:
                    sent = send_daily_report(db)
                    if sent:
                        _mark_sent_today()
                        logger.info("Gunluk rapor gonderildi")
                finally:
                    db.close()
        await asyncio.sleep(poll_seconds)
