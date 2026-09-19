from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import ParkingState, User, UserRole
from app.schemas import ParkingCapacityUpdate, ParkingStatus
from app.security import get_current_user, require_roles
from app.settings_store import get_setting, set_setting

router = APIRouter(prefix="/api/parking", tags=["parking"])

_CAPACITY_KEY = "parking_capacity"


def _get_capacity(db: Session) -> int:
    default = str(get_settings().parking_capacity)
    return int(get_setting(db, _CAPACITY_KEY, default))


@router.get("/status", response_model=ParkingStatus)
def parking_status(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    inside = db.query(ParkingState).count()
    capacity = _get_capacity(db)
    occupancy = round((inside / capacity) * 100, 1) if capacity > 0 else 0.0
    return ParkingStatus(inside=inside, capacity=capacity, occupancy_percent=occupancy)


@router.put("/capacity", response_model=ParkingStatus, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def update_capacity(payload: ParkingCapacityUpdate, db: Session = Depends(get_db)):
    if payload.capacity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Kapasite negatif olamaz")
    set_setting(db, _CAPACITY_KEY, str(payload.capacity))
    return parking_status(db=db, _=None)
