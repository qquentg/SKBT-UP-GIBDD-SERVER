from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_authorized_device, require_employee_client
from app.models.device import Device
from app.models.ban import Ban
from app.schemas.bans import ActiveBanResponse, BanResponse, BansResponse
from app.schemas.employee import (
    AssignRoleRequest,
    DeviceProfileResponse,
    RoleChangeResponse,
    RoleEventResponse,
)
from app.services.roles import assign_role, get_device_or_404, remove_role, require_role_manager
from app.services.bans import (
    ban_number,
    create_observer_ban,
    get_active_ban,
    is_ban_active,
    list_observer_bans,
)

router = APIRouter(
    prefix="/api/v1/employee",
    tags=["employee"],
    dependencies=[Depends(require_employee_client)],
)


@router.get("/me", response_model=DeviceProfileResponse)
def get_me(
    actor: Device = Depends(get_authorized_device),
) -> DeviceProfileResponse:
    return DeviceProfileResponse(device_id=actor.id, role=actor.current_role)


@router.get("/devices/{device_id}", response_model=DeviceProfileResponse)
def get_employee_device(
    device_id: UUID,
    actor: Device = Depends(get_authorized_device),
) -> DeviceProfileResponse:
    require_role_manager(actor)
    target = get_device_or_404(str(device_id))
    return DeviceProfileResponse(device_id=target.id, role=target.current_role)


@router.put("/devices/{device_id}/role", response_model=RoleChangeResponse)
def put_employee_device_role(
    device_id: UUID,
    payload: AssignRoleRequest,
    actor: Device = Depends(get_authorized_device),
) -> RoleChangeResponse:
    target = get_device_or_404(str(device_id))
    updated, action = assign_role(actor=actor, target=target, role=payload.role)
    return RoleChangeResponse(
        device_id=updated.id,
        role=updated.current_role,
        event=RoleEventResponse(action=action.value) if action is not None else None,
    )


@router.delete("/devices/{device_id}/role", response_model=RoleChangeResponse)
def delete_employee_device_role(
    device_id: UUID,
    actor: Device = Depends(get_authorized_device),
) -> RoleChangeResponse:
    target = get_device_or_404(str(device_id))
    updated, action = remove_role(actor=actor, target=target)
    return RoleChangeResponse(
        device_id=updated.id,
        role=updated.current_role,
        event=RoleEventResponse(action=action.value) if action is not None else None,
    )


@router.post("/devices/{device_id}/ban", response_model=BanResponse)
def post_employee_device_ban(
    device_id: UUID,
    actor: Device = Depends(get_authorized_device),
) -> BanResponse:
    ban = create_observer_ban(actor=actor, observer_device_id=device_id)
    return _ban_response(ban)


@router.get("/devices/{device_id}/bans", response_model=BansResponse)
def get_employee_device_bans(
    device_id: UUID,
    actor: Device = Depends(get_authorized_device),
) -> BansResponse:
    bans = list_observer_bans(actor=actor, observer_device_id=device_id)
    return BansResponse(bans=[_ban_response(ban) for ban in bans])


@router.get("/devices/{device_id}/bans/active", response_model=ActiveBanResponse)
def get_employee_device_active_ban(
    device_id: UUID,
    actor: Device = Depends(get_authorized_device),
) -> ActiveBanResponse:
    list_observer_bans(actor=actor, observer_device_id=device_id)
    ban = get_active_ban(device_id)
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
