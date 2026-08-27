from app.services import push as push_service


def auth_headers(access_token: str, client_app: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-Client-App": client_app,
    }


def register(
    client,
    client_app: str,
    fingerprint: str,
    push_token: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/devices/register",
        headers={"X-Client-App": client_app},
        json={"fingerprint_hash": fingerprint * 64, "push_token": push_token},
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


def capture_push(monkeypatch):
    sent = []

    def fake_send(notifications):
        sent.extend(notifications)

    monkeypatch.setattr(push_service, "send_push_notifications", fake_send)
    return sent


def test_eyewitness_message_pushes_to_employee_devices_with_roles(client, monkeypatch):
    sent = capture_push(monkeypatch)
    observer = register(client, "eyewitness", "a")
    chief = register(client, "employee", "b", "chief-token")
    inspector = register(client, "employee", "c", "inspector-token")
    register(client, "employee", "d", "unassigned-token")
    admin_without_push = register(client, "employee", "e")
    assign_role(client, chief, inspector, "INSPECTOR")
    assign_role(client, chief, admin_without_push, "ADMIN")
    sent.clear()

    response = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "need help"},
    )

    assert response.status_code == 200
    assert {notification.push_token for notification in sent} == {
        "chief-token",
        "inspector-token",
    }
    assert {notification.data["event"] for notification in sent} == {"message_created"}
    assert {notification.data["chat_message_type"] for notification in sent} == {"TEXT"}
    assert all(
        notification.data["observer_device_id"] == observer["device_id"]
        for notification in sent
    )


def test_employee_message_pushes_to_observer_device(client, monkeypatch):
    sent = capture_push(monkeypatch)
    observer = register(client, "eyewitness", "f", "observer-token")
    chief = register(client, "employee", "g", "chief-token")

    response = client.post(
        "/api/v1/messages",
        headers=auth_headers(chief["access_token"], "employee"),
        json={
            "observer_device_id": observer["device_id"],
            "message_type": "TEXT",
            "text": "inspector is on the way",
        },
    )

    assert response.status_code == 200
    assert [notification.push_token for notification in sent] == ["observer-token"]
    assert sent[0].title == "New employee message"
    assert sent[0].data["observer_device_id"] == observer["device_id"]


def test_ban_pushes_to_observer_and_other_chief_devices(client, monkeypatch):
    sent = capture_push(monkeypatch)
    observer = register(client, "eyewitness", "h", "observer-token")
    chief = register(client, "employee", "i", "actor-chief-token")
    second_chief = register(client, "employee", "j", "second-chief-token")
    assign_role(client, chief, second_chief, "CHIEF")
    sent.clear()

    response = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert response.status_code == 200
    assert {notification.push_token for notification in sent} == {
        "observer-token",
        "actor-chief-token",
        "second-chief-token",
    }
    assert {notification.data["event"] for notification in sent} == {"observer_banned"}
    assert {notification.title for notification in sent} == {None}
    assert {notification.body for notification in sent} == {None}
    assert all(
        notification.data["observer_device_id"] == observer["device_id"]
        for notification in sent
    )
    assert all(notification.data["started_at"] for notification in sent)
    assert all(notification.data["ends_at"] for notification in sent)
    assert {notification.data["ban_number"] for notification in sent} == {"1"}


def test_role_change_pushes_administrative_event_to_chief_devices(client, monkeypatch):
    sent = capture_push(monkeypatch)
    chief = register(client, "employee", "q", "chief-token")
    target = register(client, "employee", "r", "target-token")

    assign_role(client, chief, target, "ADMIN")

    assert [notification.push_token for notification in sent] == ["chief-token"]
    assert sent[0].title is None
    assert sent[0].body is None
    assert sent[0].data["event"] == "role_changed"
    assert sent[0].data["event_id"]
    assert sent[0].data["action"] == "ASSIGNED"
    assert sent[0].data["issued_by_device_id"] == chief["device_id"]
    assert sent[0].data["target_device_id"] == target["device_id"]
    assert sent[0].data["old_role"] == ""
    assert sent[0].data["new_role"] == "ADMIN"
    assert sent[0].data["created_at"]

    sent.clear()
    assign_role(client, chief, target, "INSPECTOR")

    assert [notification.push_token for notification in sent] == ["chief-token"]
    assert sent[0].data["action"] == "REPLACED"
    assert sent[0].data["old_role"] == "ADMIN"
    assert sent[0].data["new_role"] == "INSPECTOR"

    sent.clear()
    response = client.delete(
        f"/api/v1/employee/devices/{target['device_id']}/role",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert response.status_code == 200
    assert [notification.push_token for notification in sent] == ["chief-token"]
    assert sent[0].data["action"] == "REMOVED"
    assert sent[0].data["old_role"] == "INSPECTOR"
    assert sent[0].data["new_role"] == ""


def test_banned_observer_message_does_not_create_push(client, monkeypatch):
    sent = capture_push(monkeypatch)
    observer = register(client, "eyewitness", "m")
    chief = register(client, "employee", "n", "chief-token")
    admin = register(client, "employee", "o", "admin-token")
    inspector = register(client, "employee", "p", "inspector-token")
    assign_role(client, chief, admin, "ADMIN")
    assign_role(client, chief, inspector, "INSPECTOR")

    ban = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    sent.clear()
    message = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "message during ban"},
    )

    assert ban.status_code == 200
    assert message.status_code == 403
    assert message.json()["detail"] == "Observer device is banned"
    assert sent == []


def test_live_location_points_do_not_create_extra_pushes(client, monkeypatch):
    sent = capture_push(monkeypatch)
    observer = register(client, "eyewitness", "k")
    chief = register(client, "employee", "l", "chief-token")

    started = client.post(
        "/api/v1/messages/live-location/start",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={},
    )
    point = client.post(
        f"/api/v1/messages/{started.json()['message_id']}/live-location/points",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"latitude": 55.7558, "longitude": 37.6173},
    )

    assert started.status_code == 200
    assert point.status_code == 200
    assert [notification.push_token for notification in sent] == ["chief-token"]
    assert sent[0].data["chat_message_type"] == "LIVE_LOCATION"
