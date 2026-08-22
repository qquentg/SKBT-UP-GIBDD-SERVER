from datetime import UTC, datetime, timedelta

from app.models.ban import Ban
from app.models.device import utc_now


def auth_headers(access_token: str, client_app: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Client-App": client_app,
    }


def register(client, client_app: str, fingerprint: str) -> dict:
    response = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": client_app},
        json={"fingerprint_hash": fingerprint * 64},
    )
    assert response.status_code == 200
    return response.json()


def assign_role(client, actor: dict, target: dict, role: str) -> dict:
    response = client.put(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(actor["access_token"], "employee"),
        json={"role": role},
    )
    assert response.status_code == 200
    return response.json()


def test_inspector_can_ban_observer_and_block_messages(client):
    observer = register(client, "eyewitness", "A")
    chief = register(client, "employee", "B")
    inspector = register(client, "employee", "C")
    assign_role(client, chief, inspector, "INSPECTOR")

    banned = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(inspector["access_token"], "employee"),
    )
    blocked_message = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "blocked"},
    )
    employee_answer = client.post(
        "/api/v1/messages",
        headers=auth_headers(inspector["access_token"], "employee"),
        json={
            "observer_device_id": observer["device_id"],
            "message_type": "TEXT",
            "text": "answer",
        },
    )

    assert banned.status_code == 200
    assert banned.json()["observer_device_id"] == observer["device_id"]
    assert banned.json()["issued_by_device_id"] == inspector["device_id"]
    assert banned.json()["ban_number"] == 1
    assert banned.json()["is_active"] is True
    assert banned.json()["ends_at"] is not None
    assert Ban.select().count() == 1

    started_at = datetime.fromisoformat(
        banned.json()["started_at"].replace("Z", "+00:00")
    )
    ends_at = datetime.fromisoformat(banned.json()["ends_at"].replace("Z", "+00:00"))
    assert timedelta(hours=23, minutes=59) < ends_at - started_at < timedelta(
        days=1, minutes=1
    )

    assert blocked_message.status_code == 403
    assert blocked_message.json()["detail"] == "Observer device is banned"

    assert employee_answer.status_code == 200
    assert employee_answer.json()["observer_device_id"] == observer["device_id"]


def test_repeated_active_ban_does_not_escalate(client):
    observer = register(client, "eyewitness", "D")
    chief = register(client, "employee", "E")

    first = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    repeated = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert first.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json()["ban_id"] == first.json()["ban_id"]
    assert repeated.json()["ban_number"] == 1
    assert Ban.select().count() == 1


def test_chief_sees_banned_chat_and_inspector_does_not(client):
    observer = register(client, "eyewitness", "M")
    chief = register(client, "employee", "N")
    inspector = register(client, "employee", "O")
    assign_role(client, chief, inspector, "INSPECTOR")

    message = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "visible before ban"},
    )
    ban = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    chief_chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    inspector_chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(inspector["access_token"], "employee"),
    )

    assert message.status_code == 200
    assert ban.status_code == 200

    assert chief_chats.status_code == 200
    assert chief_chats.json()["chats"][0]["observer_device_id"] == observer["device_id"]
    assert chief_chats.json()["chats"][0]["active_ban"]["ban_id"] == ban.json()["ban_id"]
    assert chief_chats.json()["chats"][0]["active_ban"]["is_active"] is True

    assert inspector_chats.status_code == 200
    assert inspector_chats.json() == {"chats": []}


def test_ban_history_escalates_to_permanent(client):
    observer = register(client, "eyewitness", "F")
    chief = register(client, "employee", "G")

    first = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    ).json()
    Ban.update(ends_at=utc_now() - timedelta(seconds=1)).where(
        Ban.id == first["ban_id"]
    ).execute()

    second = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    ).json()
    Ban.update(ends_at=utc_now() - timedelta(seconds=1)).where(
        Ban.id == second["ban_id"]
    ).execute()

    third = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    history = client.get(
        f"/api/v1/employee/devices/{observer['device_id']}/bans",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert third.status_code == 200
    assert third.json()["ban_number"] == 3
    assert third.json()["ends_at"] is None
    assert third.json()["is_active"] is True

    assert history.status_code == 200
    assert [ban["ban_number"] for ban in history.json()["bans"]] == [3, 2, 1]


def test_active_ban_endpoint_returns_null_when_no_active_ban(client):
    observer = register(client, "eyewitness", "H")
    chief = register(client, "employee", "I")

    response = client.get(
        f"/api/v1/employee/devices/{observer['device_id']}/bans/active",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert response.status_code == 200
    assert response.json() == {"ban": None}


def test_employee_without_role_cannot_ban(client):
    observer = register(client, "eyewitness", "J")
    register(client, "employee", "K")
    employee = register(client, "employee", "L")

    response = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(employee["access_token"], "employee"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Ban is not allowed for this device"
