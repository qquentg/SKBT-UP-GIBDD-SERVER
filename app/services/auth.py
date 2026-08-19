import hashlib
import secrets

from app.models.device import Device


def hash_access_token(access_token: str) -> str:
    return hashlib.sha256(access_token.encode("utf-8")).hexdigest()


def issue_access_token(device: Device) -> str:
    access_token = secrets.token_urlsafe(32)
    Device.update(access_token_hash=hash_access_token(access_token)).where(
        Device.id == device.id
    ).execute()
    return access_token


def get_device_by_access_token(access_token: str) -> Device | None:
    token_hash = hash_access_token(access_token)
    return Device.get_or_none(Device.access_token_hash == token_hash)
