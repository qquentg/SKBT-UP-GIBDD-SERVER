from app.models.device import Device
from app.models.role_event import RoleEvent
from app.services.auth import hash_access_token


def auth_headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Client-App": "employee",
    }


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
    assert first.json()["access_token"]
    assert second.json()["access_token"]
    assert first.json()["access_token"] != second.json()["access_token"]
    assert Device.select().count() == 1

    device = Device.get()
    assert device.access_token_hash == hash_access_token(second.json()["access_token"])
    assert device.access_token_hash != second.json()["access_token"]


def test_repeated_registration_updates_push_token(client):
    payload = {"fingerprint_hash": "n" * 64, "push_token": "old-token"}

    first = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "eyewitness"},
        json=payload,
    )
    second = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "eyewitness"},
        json={"fingerprint_hash": "n" * 64, "push_token": "new-token"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["device_id"] == second.json()["device_id"]
    assert Device.get_by_id(first.json()["device_id"]).push_token == "new-token"


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


def test_employee_me_requires_valid_token(client):
    response = client.get(
        "/api/v1/employee/me",
        headers={"X-Client-App": "employee"},
    )

    assert response.status_code == 401

    registration = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "g" * 64},
    ).json()

    response = client.get(
        "/api/v1/employee/me",
        headers=auth_headers(registration["access_token"]),
    )

    assert response.status_code == 200
    assert response.json() == {
        "device_id": registration["device_id"],
        "role": "CHIEF",
    }


def test_chief_can_assign_replace_and_remove_roles(client):
    chief = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "h" * 64},
    ).json()
    target = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "i" * 64},
    ).json()

    lookup = client.get(
        f"/api/v1/employee/devices/{target['device_id']}",
        headers=auth_headers(chief["access_token"]),
    )
    assigned = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "ADMIN"},
    )
    repeated = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "ADMIN"},
    )
    replaced = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "INSPECTOR"},
    )
    removed = client.delete(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
    )

    assert lookup.status_code == 200
    assert lookup.json()["role"] is None

    assert assigned.status_code == 200
    assert assigned.json()["role"] == "ADMIN"
    assert assigned.json()["event"]["action"] == "ASSIGNED"

    assert repeated.status_code == 200
    assert repeated.json()["role"] == "ADMIN"
    assert repeated.json()["event"] is None

    assert replaced.status_code == 200
    assert replaced.json()["role"] == "INSPECTOR"
    assert replaced.json()["event"]["action"] == "REPLACED"

    assert removed.status_code == 200
    assert removed.json()["role"] is None
    assert removed.json()["event"]["action"] == "REMOVED"

    events = list(RoleEvent.select().order_by(RoleEvent.created_at))
    assert [event.action for event in events] == [
        "AUTO_ASSIGNED",
        "ASSIGNED",
        "REPLACED",
        "REMOVED",
    ]
    assert events[-1].role == "INSPECTOR"


def test_chief_and_admin_can_list_employee_devices(client):
    chief = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "o" * 64},
    ).json()
    admin = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "p" * 64},
    ).json()
    inspector = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "q" * 64},
    ).json()
    client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "eyewitness"},
        json={"fingerprint_hash": "r" * 64},
    )

    client.put(
        f"/api/v1/employee/devices/{admin['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "ADMIN"},
    )
    client.put(
        f"/api/v1/employee/devices/{inspector['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "INSPECTOR"},
    )

    chief_response = client.get(
        "/api/v1/employee/devices",
        headers=auth_headers(chief["access_token"]),
    )
    admin_response = client.get(
        "/api/v1/employee/devices",
        headers=auth_headers(admin["access_token"]),
    )
    inspector_response = client.get(
        "/api/v1/employee/devices",
        headers=auth_headers(inspector["access_token"]),
    )

    assert chief_response.status_code == 200
    assert admin_response.status_code == 200
    assert inspector_response.status_code == 403

    assert {device["device_id"] for device in chief_response.json()["devices"]} == {
        chief["device_id"],
        admin["device_id"],
        inspector["device_id"],
    }
    assert {device["role"] for device in admin_response.json()["devices"]} == {
        "CHIEF",
        "ADMIN",
        "INSPECTOR",
    }
    assert all(
        device["last_activity_at"] is not None
        for device in chief_response.json()["devices"]
    )


def test_admin_cannot_assign_chief(client):
    chief = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "j" * 64},
    ).json()
    admin = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "k" * 64},
    ).json()
    target = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "l" * 64},
    ).json()

    admin_assignment = client.put(
        f"/api/v1/employee/devices/{admin['device_id']}/role",
        headers=auth_headers(chief["access_token"]),
        json={"role": "ADMIN"},
    )
    forbidden = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(admin["access_token"]),
        json={"role": "CHIEF"},
    )
    allowed = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(admin["access_token"]),
        json={"role": "INSPECTOR"},
    )

    assert admin_assignment.status_code == 200
    assert forbidden.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["role"] == "INSPECTOR"


def test_unregistered_device_lookup_returns_404(client):
    chief = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": "employee"},
        json={"fingerprint_hash": "m" * 64},
    ).json()

    response = client.get(
        "/api/v1/employee/devices/00000000-0000-0000-0000-000000000000",
        headers=auth_headers(chief["access_token"]),
    )

    assert response.status_code == 404
