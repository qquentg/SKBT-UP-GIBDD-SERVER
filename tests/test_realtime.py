import pytest
from starlette.websockets import WebSocketDisconnect


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


def test_websocket_requires_authorization(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(
            "/api/v1/realtime",
            headers={"X-Client-App": "employee"},
        ):
            pass

    assert exc.value.code == 1008


def test_employee_websocket_receives_eyewitness_text_message(client):
    observer = register(client, "eyewitness", "a")
    chief = register(client, "employee", "b")

    with client.websocket_connect(
        "/api/v1/realtime",
        headers=auth_headers(chief["access_token"], "employee"),
    ) as websocket:
        connected = websocket.receive_json()
        assert connected == {
            "event": "connected",
            "device_id": chief["device_id"],
            "client_app": "employee",
            "role": "CHIEF",
        }

        created = client.post(
            "/api/v1/messages",
            headers=auth_headers(observer["access_token"], "eyewitness"),
            json={"message_type": "TEXT", "text": "need help"},
        )
        event = websocket.receive_json()

    assert created.status_code == 200
    assert event["event"] == "message_created"
    assert event["message"]["message_id"] == created.json()["message_id"]
    assert event["message"]["observer_device_id"] == observer["device_id"]
    assert event["message"]["sender_device_id"] == observer["device_id"]
    assert event["message"]["message_type"] == "TEXT"
    assert event["message"]["text"] == "need help"


def test_observer_websocket_receives_employee_answer(client):
    observer = register(client, "eyewitness", "c")
    chief = register(client, "employee", "d")

    with client.websocket_connect(
        "/api/v1/realtime",
        headers=auth_headers(observer["access_token"], "eyewitness"),
    ) as websocket:
        connected = websocket.receive_json()
        assert connected["event"] == "connected"
        assert connected["client_app"] == "eyewitness"

        answer = client.post(
            "/api/v1/messages",
            headers=auth_headers(chief["access_token"], "employee"),
            json={
                "observer_device_id": observer["device_id"],
                "message_type": "TEXT",
                "text": "inspector is coming",
            },
        )
        event = websocket.receive_json()

    assert answer.status_code == 200
    assert event["event"] == "message_created"
    assert event["message"]["message_id"] == answer.json()["message_id"]
    assert event["message"]["sender_device_id"] == chief["device_id"]


def test_websocket_receives_live_location_point(client):
    observer = register(client, "eyewitness", "e")
    chief = register(client, "employee", "f")

    with client.websocket_connect(
        "/api/v1/realtime",
        headers=auth_headers(chief["access_token"], "employee"),
    ) as websocket:
        websocket.receive_json()
        started = client.post(
            "/api/v1/messages/live-location/start",
            headers=auth_headers(observer["access_token"], "eyewitness"),
            json={},
        )
        message_created = websocket.receive_json()

        point = client.post(
            f"/api/v1/messages/{started.json()['message_id']}/live-location/points",
            headers=auth_headers(observer["access_token"], "eyewitness"),
            json={"latitude": 55.7558, "longitude": 37.6173},
        )
        point_event = websocket.receive_json()

    assert started.status_code == 200
    assert point.status_code == 200
    assert message_created["event"] == "message_created"
    assert message_created["message"]["message_type"] == "LIVE_LOCATION"
    assert point_event["event"] == "live_location_point"
    assert point_event["message_id"] == started.json()["message_id"]
    assert point_event["point"] == point.json()


def test_ban_realtime_notifies_observer_and_chief(client, monkeypatch):
    from app.services import realtime

    published_devices = []
    published_roles = []

    def capture_devices(device_ids, event):
        published_devices.append((device_ids, event))

    def capture_employee_roles(roles, event):
        published_roles.append((roles, event))

    observer = register(client, "eyewitness", "j")
    chief = register(client, "employee", "k")
    monkeypatch.setattr(
        realtime.manager,
        "publish_to_devices",
        capture_devices,
    )
    monkeypatch.setattr(
        realtime.manager,
        "publish_to_employee_roles",
        capture_employee_roles,
    )

    ban = client.post(
        f"/api/v1/employee/devices/{observer['device_id']}/ban",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    assert ban.status_code == 200

    started = client.post(
        "/api/v1/messages/live-location/start",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={},
    )

    assert published_devices[0][0] == {observer["device_id"]}
    assert published_devices[0][1]["event"] == "observer_banned"
    assert published_roles[0][0] == {"CHIEF"}
    assert published_roles[0][1]["event"] == "observer_banned"

    assert started.status_code == 403
    assert started.json()["detail"] == "Observer device is banned"


def test_employee_websocket_uses_current_role_after_role_assignment(client):
    observer = register(client, "eyewitness", "g")
    chief = register(client, "employee", "h")
    employee = register(client, "employee", "i")

    with client.websocket_connect(
        "/api/v1/realtime",
        headers=auth_headers(employee["access_token"], "employee"),
    ) as websocket:
        connected = websocket.receive_json()
        assert connected["role"] is None

        assigned = client.put(
            f"/api/v1/employee/devices/{employee['device_id']}/role",
            headers=auth_headers(chief["access_token"], "employee"),
            json={"role": "INSPECTOR"},
        )
        role_event = websocket.receive_json()

        created = client.post(
            "/api/v1/messages",
            headers=auth_headers(observer["access_token"], "eyewitness"),
            json={"message_type": "TEXT", "text": "now visible"},
        )
        message_event = websocket.receive_json()

    assert assigned.status_code == 200
    assert role_event == {
        "event": "role_changed",
        "actor_device_id": chief["device_id"],
        "target_device_id": employee["device_id"],
        "action": "ASSIGNED",
        "role": "INSPECTOR",
    }
    assert created.status_code == 200
    assert message_event["event"] == "message_created"
    assert message_event["message"]["message_id"] == created.json()["message_id"]
