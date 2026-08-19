from app.models.device import Device
from app.models.role_event import RoleEvent


def test_health(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_eyewitness_registration_is_idempotent(client):
    payload = {"fingerprint_hash": "a" * 64}

    first = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "eyewitness"},
        json=payload,
    )
    second = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "eyewitness"},
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["device_id"] == second.json()["device_id"]
    assert first.json()["role"] is None
    assert second.json()["role"] is None
    assert Device.select().count() == 1


def test_first_employee_bootstraps_chief_once(client):
    first = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "b" * 64},
    )
    second = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "c" * 64},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["role"] == "CHIEF"
    assert second.json()["role"] is None

    assert Device.select().where(Device.current_role == "CHIEF").count() == 1
    assert RoleEvent.select().count() == 1

    event = RoleEvent.get()
    assert event.actor_device is None
    assert event.action == "AUTO_ASSIGNED"
    assert event.role == "CHIEF"


def test_multiple_chief_devices_are_allowed(client):
    first = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "e" * 64},
    )
    second_device = Device.create(
        fingerprint_hash="f" * 64,
        current_role="CHIEF",
    )

    assert first.status_code == 200
    assert first.json()["role"] == "CHIEF"
    assert second_device.current_role == "CHIEF"
    assert Device.select().where(Device.current_role == "CHIEF").count() == 2


def test_invalid_client_app_is_rejected(client):
    response = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "unknown"},
        json={"fingerprint_hash": "d" * 64},
    )

    assert response.status_code == 422
