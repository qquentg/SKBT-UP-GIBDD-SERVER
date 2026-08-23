from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.schemas.device import ClientApp
from app.services.auth import get_device_by_access_token
from app.services.realtime import manager

router = APIRouter(tags=["realtime"])


@router.websocket("/api/v1/realtime")
async def realtime(websocket: WebSocket) -> None:
    client_app = _client_app_from_header(websocket)
    device = _device_from_authorization(websocket)
    if client_app is None or device is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    connection = manager.connect(device=device, client_app=client_app)
    try:
        await websocket.send_json(
            {
                "event": "connected",
                "device_id": str(device.id),
                "client_app": client_app.value,
                "role": device.current_role,
            }
        )
        while True:
            event = await connection.queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(connection)


def _client_app_from_header(websocket: WebSocket) -> ClientApp | None:
    raw_value = websocket.headers.get("x-client-app")
    try:
        return ClientApp(raw_value)
    except ValueError:
        return None


def _device_from_authorization(websocket: WebSocket):
    authorization = websocket.headers.get("authorization")
    if authorization is None:
        return None

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None

    return get_device_by_access_token(token)
