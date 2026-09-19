import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.database import Base, engine
from app.routers import auth, cameras, detect, logs, parking, reports, users, watchlist
from app.scheduler import daily_report_loop
from app.websocket_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    task = asyncio.create_task(daily_report_loop())
    yield
    task.cancel()


app = FastAPI(title="Sertek ALPR - Plaka Tanima Platformu", version="1.0.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(cameras.router)
app.include_router(watchlist.router)
app.include_router(detect.router)
app.include_router(logs.router)
app.include_router(reports.router)
app.include_router(parking.router)


@app.websocket("/ws/alerts")
async def alerts_socket(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


app.mount("/", StaticFiles(directory="static", html=True), name="static")
