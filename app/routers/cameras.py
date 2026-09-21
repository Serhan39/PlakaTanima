import cv2
from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Camera, RelayEventLog, User, UserRole
from app.outputs.relay import build_relay_driver
from app.schemas import CameraCreate, CameraRead, RelayTestResult
from app.security import get_current_user, require_roles

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Camera).order_by(Camera.id).all()


@router.get("/{camera_id}/preview")
def camera_preview(camera_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Kameranin RTSP adresinden tek bir kare cekip JPEG olarak dondurur;
    panelde 'Canli Kamera' kucuk onizlemesi icin periyodik olarak cagrilir."""
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")
    if not camera.rtsp_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bu kamera icin RTSP adresi tanimli degil")

    capture = cv2.VideoCapture(camera.rtsp_url)
    ok, frame = capture.read()
    capture.release()
    if not ok:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Kameradan goruntu alinamadi")

    ok, buffer = cv2.imencode(".jpg", frame)
    if not ok:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Goruntu kodlanamadi")
    return Response(content=buffer.tobytes(), media_type="image/jpeg")


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


@router.post(
    "/{camera_id}/test-relay",
    response_model=RelayTestResult,
    dependencies=[Depends(require_roles(UserRole.ADMIN, UserRole.OPERATOR))],
)
def test_relay(camera_id: int, db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")

    driver = build_relay_driver(camera)
    success, message = driver.trigger_open(camera.relay_pulse_seconds)

    db.add(RelayEventLog(camera_id=camera.id, triggered_by="manual", success=success, message=message))
    db.commit()
    return RelayTestResult(success=success, message=message)
