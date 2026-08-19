from fastapi import APIRouter, Header

from app.schemas.device import ClientApp, DeviceRegisterRequest, DeviceRegisterResponse
from app.services.devices import register_device

router = APIRouter(prefix="/api/v1/devices", tags=["devices"])


@router.post("/register", response_model=DeviceRegisterResponse)
def register(
    payload: DeviceRegisterRequest,
    client_app: ClientApp = Header(alias="X-Client-App"),
) -> DeviceRegisterResponse:
    device, access_token = register_device(
        fingerprint_hash=payload.fingerprint_hash,
        client_app=client_app,
        push_token=payload.push_token,
    )

    return DeviceRegisterResponse(
        device_id=device.id,
        role=device.current_role,
        access_token=access_token,
    )
