from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, User, UserRole
from app.schemas import CameraCreate, CameraRead
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Camera).order_by(Camera.id).all()


@router.post("", response_model=CameraRead, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def create_camera(payload: CameraCreate, db: Session = Depends(get_db)):
    camera = Camera(**payload.model_dump())
    db.add(camera)
    db.commit()
    db.refresh(camera)
    return camera


@router.delete("/{camera_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_roles(UserRole.ADMIN))])
def delete_camera(camera_id: int, db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")
    db.delete(camera)
    db.commit()
