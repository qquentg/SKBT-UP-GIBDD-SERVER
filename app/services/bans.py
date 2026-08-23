from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status

from app.db.database import database_proxy
from app.models.ban import Ban
from app.models.device import Device, utc_now
from app.services.push import notify_observer_banned
from app.services.realtime import publish_observer_banned

BAN_ISSUER_ROLES = {"INSPECTOR", "ADMIN", "CHIEF"}
FIRST_BAN_DURATION = timedelta(days=1)
SECOND_BAN_DURATION = timedelta(days=30)


def require_ban_issuer(actor: Device) -> None:
    if actor.current_role not in BAN_ISSUER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ban is not allowed for this device",
        )


def create_observer_ban(*, actor: Device, observer_device_id: UUID) -> Ban:
    require_ban_issuer(actor)
    observer = _get_device_or_404(observer_device_id)

    active_ban = get_active_ban(observer.id)
    if active_ban is not None:
        return active_ban

    existing_bans_count = Ban.select().where(Ban.observer_device == observer.id).count()
    started_at = utc_now()
    ends_at = _ban_ends_at(
        started_at=started_at,
        existing_bans_count=existing_bans_count,
    )

    with database_proxy.atomic():
        ban = Ban.create(
            observer_device=observer.id,
            issued_by_device=actor.id,
            started_at=started_at,
            ends_at=ends_at,
        )
        Device.update(last_activity_at=started_at).where(Device.id == actor.id).execute()

    notify_observer_banned(ban, actor_device_id=actor.id)
    publish_observer_banned(ban, actor_device_id=actor.id)
    return ban


def list_observer_bans(*, actor: Device, observer_device_id: UUID) -> list[Ban]:
    require_ban_issuer(actor)
    observer = _get_device_or_404(observer_device_id)
    return list(
        Ban.select()
        .where(Ban.observer_device == observer.id)
        .order_by(Ban.started_at.desc(), Ban.id.desc())
    )


def get_active_ban(observer_device_id: UUID) -> Ban | None:
    now = utc_now()
    for ban in (
        Ban.select()
        .where(Ban.observer_device == observer_device_id)
        .order_by(Ban.started_at.desc(), Ban.id.desc())
    ):
        if _is_ban_active(ban=ban, now=now):
            return ban
    return None


def get_ban_at(observer_device_id: UUID, moment: datetime) -> Ban | None:
    for ban in (
        Ban.select()
        .where(Ban.observer_device == observer_device_id)
        .order_by(Ban.started_at.desc(), Ban.id.desc())
    ):
        if _is_ban_active(ban=ban, now=_as_utc_aware(moment)):
            return ban
    return None


def ban_number(ban: Ban) -> int:
    return (
        Ban.select()
        .where(
            (Ban.observer_device == ban.observer_device_id)
            & (Ban.started_at <= ban.started_at)
        )
        .count()
    )


def is_ban_active(ban: Ban) -> bool:
    return _is_ban_active(ban=ban, now=utc_now())


def _ban_ends_at(*, started_at: datetime, existing_bans_count: int) -> datetime | None:
    if existing_bans_count == 0:
        return started_at + FIRST_BAN_DURATION
    if existing_bans_count == 1:
        return started_at + SECOND_BAN_DURATION
    return None


def _is_ban_active(*, ban: Ban, now: datetime) -> bool:
    if _as_utc_aware(ban.started_at) > now:
        return False
    return ban.ends_at is None or _as_utc_aware(ban.ends_at) > now


def _get_device_or_404(device_id: UUID) -> Device:
    device = Device.get_or_none(Device.id == device_id)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Observer device not found",
        )
    return device


def _as_utc_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=_local_timezone()).astimezone(UTC)
    return value.astimezone(UTC)


def _local_timezone():
    return datetime.now().astimezone().tzinfo
