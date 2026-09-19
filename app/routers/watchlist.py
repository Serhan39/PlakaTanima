from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.crypto import decrypt_text, deterministic_hash, encrypt_text
from app.database import get_db
from app.models import User, UserRole, WatchlistEntry
from app.plate_utils import format_plate, is_valid_turkish_plate
from app.schemas import WatchlistCreate, WatchlistRead
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _to_read(entry: WatchlistEntry) -> WatchlistRead:
    return WatchlistRead(
        id=entry.id,
        plate=decrypt_text(entry.plate_encrypted),
        category=entry.category,
        note=decrypt_text(entry.note_encrypted) if entry.note_encrypted else "",
        created_at=entry.created_at,
    )


@router.get("", response_model=list[WatchlistRead])
def list_watchlist(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return [_to_read(e) for e in db.query(WatchlistEntry).order_by(WatchlistEntry.id.desc()).all()]


@router.post("", response_model=WatchlistRead, dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))])
def create_entry(payload: WatchlistCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if not is_valid_turkish_plate(payload.plate):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Gecerli bir Turkiye plakasi girin")

    plate = format_plate(payload.plate)
    plate_hash = deterministic_hash(plate)
    if db.query(WatchlistEntry).filter(WatchlistEntry.plate_hash == plate_hash).first():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu plaka zaten listede")

    entry = WatchlistEntry(
        plate_encrypted=encrypt_text(plate),
        plate_hash=plate_hash,
        category=payload.category,
        note_encrypted=encrypt_text(payload.note) if payload.note else "",
        created_by=user.id,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return _to_read(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))])
def delete_entry(entry_id: int, db: Session = Depends(get_db)):
    entry = db.get(WatchlistEntry, entry_id)
    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kayit bulunamadi")
    db.delete(entry)
    db.commit()
