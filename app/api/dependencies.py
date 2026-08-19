from typing import Annotated

from fastapi import Header, HTTPException, status

from app.models.device import Device
from app.schemas.device import ClientApp
from app.services.auth import get_device_by_access_token


def get_authorized_device(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> Device:
    if authorization is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token is required",
        )

    device = get_device_by_access_token(token)
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        )

    return device


def require_employee_client(
    client_app: Annotated[ClientApp, Header(alias="X-Client-App")],
) -> None:
    if client_app != ClientApp.EMPLOYEE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employee client is required",
        )
