from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)

    async def broadcast(self, message: dict) -> None:
        for connection in list(self._connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()
equipment_manager = ConnectionManager()


async def broadcast_detection(message: dict) -> None:
    await manager.broadcast(message)


async def broadcast_equipment_event(message: dict) -> None:
    await equipment_manager.broadcast(message)
