from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.dependencies import get_authorized_device, require_employee_client
from app.models.device import Device
from app.schemas.employee import (
    AssignRoleRequest,
    DeviceProfileResponse,
    RoleChangeResponse,
    RoleEventResponse,
)
from app.services.roles import assign_role, get_device_or_404, remove_role, require_role_manager

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
