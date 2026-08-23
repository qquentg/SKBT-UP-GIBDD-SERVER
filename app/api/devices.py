from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.api.dependencies import get_authorized_device
from app.models.ban import Ban
from app.models.device import Device
from app.schemas.bans import ActiveBanResponse, BanResponse
from app.schemas.device import ClientApp, DeviceRegisterRequest, DeviceRegisterResponse
from app.services.bans import ban_number, get_active_ban, is_ban_active
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


@router.get("/me/bans/active", response_model=ActiveBanResponse)
def get_own_active_ban(
    client_app: ClientApp = Header(alias="X-Client-App"),
    actor: Device = Depends(get_authorized_device),
) -> ActiveBanResponse:
    if client_app != ClientApp.EYEWITNESS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This endpoint is only for eyewitness devices",
        )

    ban = get_active_ban(actor.id)
    return ActiveBanResponse(ban=_ban_response(ban) if ban is not None else None)


def _ban_response(ban: Ban) -> BanResponse:
    return BanResponse(
        ban_id=ban.id,
        observer_device_id=ban.observer_device_id,
        issued_by_device_id=ban.issued_by_device_id,
        started_at=ban.started_at,
        ends_at=ban.ends_at,
        ban_number=ban_number(ban),
        is_active=is_ban_active(ban),
    )
