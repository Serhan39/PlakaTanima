import asyncio

import cv2
from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.live_frame_cache import get_frame, set_frame
from app.models import Camera, RelayEventLog, User, UserRole
from app.outputs.relay import build_relay_driver
from app.schemas import CameraCreate, CameraRead, RelayTestResult, StreamTokenRead
from app.security import get_current_user, require_roles
from app.stream_tokens import mint_token, resolve_token

router = APIRouter(prefix="/api/cameras", tags=["cameras"])

_STREAM_FRAME_INTERVAL_SECONDS = 0.1  # panelde ~10 kare/sn hedefi
_STREAM_FIRST_FRAME_TIMEOUT_SECONDS = 10  # bu sure icinde hic kare gelmezse akisi sonlandir


@router.get("", response_model=list[CameraRead])
def list_cameras(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Camera).order_by(Camera.id).all()


@router.get("/{camera_id}/preview")
def camera_preview(camera_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Kameranin en son karesini dondurur; panelde 'Canli Kameralar' izgarasi
    tarafindan periyodik olarak cagrilir.

    Once bellekteki onbellege bakar (app/camera_worker.py, zaten tespit icin
    actigi RTSP baglantisindan okudugu her kareyi buraya da yaziyor) - bu,
    anlik ve ek kamera baglantisi gerektirmiyor. camera_worker henuz hic kare
    gondermemisse (yeni eklenmis kamera, worker henuz yeniden baslamamis vb.)
    tek seferlik dogrudan RTSP baglantisiyla geriye duser."""
    camera = db.get(Camera, camera_id)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")

    cached = get_frame(camera_id)
    if cached is not None:
        return Response(content=cached, media_type="image/jpeg")

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


@router.post("/{camera_id}/stream-token", response_model=StreamTokenRead)
def create_stream_token(camera_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Panelin <img> etiketiyle dogrudan baglanacagi /stream ucu icin,
    normal JWT ile kimligi dogrulanmis bir istemciye kisa omurlu, sadece
    bu kameranin goruntusunu almaya yeten bir token verir - boylece asil
    JWT hicbir zaman URL/tarayici gecmisine sizmaz."""
    if not db.get(Camera, camera_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")
    return StreamTokenRead(token=mint_token(camera_id))


@router.get("/{camera_id}/stream")
async def camera_stream(camera_id: int, token: str, request: Request, db: Session = Depends(get_db)):
    """Gercek zamanli, akici canli goruntu icin MJPEG (multipart/x-mixed-replace)
    akisi - tarayici <img src="..."> etiketiyle bunu native olarak
    oynatir, ek JS/polling gerekmez. Kimlik dogrulama Authorization header'i
    yerine (img etiketi bunu tasiyamaz) kisa omurlu bir stream token ile
    yapilir (bkz. POST /stream-token, app/stream_tokens.py).

    Onbellekteki en son kareyi (app/camera_worker.py'nin surekli yazdigi)
    periyodik olarak yayinlar - ekstra kamera baglantisi acmaz.

    Onbellekte henuz hic kare yoksa (worker henuz baslamamis, kameraya
    baglanamiyor, ya da eski bir imajla calisiyor), sonsuza kadar sessizce
    beklemek yerine _STREAM_FIRST_FRAME_TIMEOUT_SECONDS sonra akisi
    kapatir - boylece tarayicida "Baglaniliyor..." sonsuza kadar asili
    kalmak yerine bir hata/yeniden baglanma dongusune girer."""
    if resolve_token(token) != camera_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Gecersiz veya suresi dolmus token")
    if not db.get(Camera, camera_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")

    async def frame_generator():
        got_first_frame = False
        waited_seconds = 0.0
        while True:
            if await request.is_disconnected():
                break
            frame = get_frame(camera_id)
            if frame is not None:
                got_first_frame = True
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    b"Content-Length: " + str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n"
                )
            elif not got_first_frame:
                waited_seconds += _STREAM_FRAME_INTERVAL_SECONDS
                if waited_seconds >= _STREAM_FIRST_FRAME_TIMEOUT_SECONDS:
                    print(f"[api] Kamera {camera_id} icin {_STREAM_FIRST_FRAME_TIMEOUT_SECONDS}sn'de hic kare gelmedi, akis kapatiliyor")
                    break
            await asyncio.sleep(_STREAM_FRAME_INTERVAL_SECONDS)

    return StreamingResponse(frame_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.post("/{camera_id}/live-frame", status_code=status.HTTP_204_NO_CONTENT)
async def push_live_frame(
    camera_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """app/camera_worker.py'nin, tespit icin zaten cektigi kareyi canli
    onizleme onbellegine yazmak icin cagirdigi uc. Ekstra dogrulama/kod
    cozme yapmiyor - worker JPEG'i oldugu gibi buraya iletiyor."""
    if not db.get(Camera, camera_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kamera bulunamadi")
    data = await file.read()
    set_frame(camera_id, data)


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
