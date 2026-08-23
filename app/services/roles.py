from fastapi import HTTPException, status

from app.db.database import database_proxy
from app.models.device import Device, utc_now
from app.models.role_event import RoleEvent
from app.schemas.device import DeviceRole, RoleAction
from app.services.realtime import publish_role_changed

ROLE_ASSIGNMENT_RIGHTS = {
    DeviceRole.ADMIN.value: {DeviceRole.INSPECTOR.value, DeviceRole.ADMIN.value},
    DeviceRole.CHIEF.value: {
        DeviceRole.INSPECTOR.value,
        DeviceRole.ADMIN.value,
        DeviceRole.CHIEF.value,
    },
}


def require_role_manager(actor: Device, target_role: DeviceRole | None = None) -> None:
    allowed_roles = ROLE_ASSIGNMENT_RIGHTS.get(actor.current_role)
    if allowed_roles is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Role management is not allowed for this device",
        )

    if target_role is not None and target_role.value not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This role cannot be assigned by the current device",
        )


def get_device_or_404(device_id: str) -> Device:
    device = Device.get_or_none(Device.id == device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device not found",
        )
    return device


def list_employee_devices(actor: Device) -> list[Device]:
    require_role_manager(actor)
    return list(
        Device.select()
        .where(Device.current_role.is_null(False))
        .order_by(Device.current_role.asc(), Device.last_activity_at.desc())
    )


def assign_role(
    *,
    actor: Device,
    target: Device,
    role: DeviceRole,
) -> tuple[Device, RoleAction | None]:
    require_role_manager(actor, role)
    old_role = target.current_role
    if old_role == role.value:
        return target, None

    action = RoleAction.ASSIGNED if old_role is None else RoleAction.REPLACED
    with database_proxy.atomic():
        Device.update(current_role=role.value, last_activity_at=utc_now()).where(
            Device.id == target.id
        ).execute()
        RoleEvent.create(
            actor_device=actor.id,
            target_device=target.id,
            action=action.value,
            role=role.value,
        )

    updated = Device.get_by_id(target.id)
    publish_role_changed(
        actor_device_id=actor.id,
        target_device_id=target.id,
        action=action.value,
        role=role.value,
    )
    return updated, action


def remove_role(*, actor: Device, target: Device) -> tuple[Device, RoleAction | None]:
    require_role_manager(actor)
    removed_role = target.current_role
    if removed_role is None:
        return target, None

    with database_proxy.atomic():
        Device.update(current_role=None, last_activity_at=utc_now()).where(
            Device.id == target.id
        ).execute()
        RoleEvent.create(
            actor_device=actor.id,
            target_device=target.id,
            action=RoleAction.REMOVED.value,
            role=removed_role,
        )

    updated = Device.get_by_id(target.id)
    publish_role_changed(
        actor_device_id=actor.id,
        target_device_id=target.id,
        action=RoleAction.REMOVED.value,
        role=removed_role,
    )
    return updated, RoleAction.REMOVED
