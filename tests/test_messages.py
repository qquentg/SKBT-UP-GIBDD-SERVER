from app.models.message import Message


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


def test_eyewitness_sends_text_and_employee_reads_chat(client):
    observer = register(client, "eyewitness", "a")
    chief = register(client, "employee", "b")

    created = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "Нужна помощь на дороге"},
    )
    chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    messages = client.get(
        f"/api/v1/chats/{observer['device_id']}/messages",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert created.status_code == 200
    assert created.json()["observer_device_id"] == observer["device_id"]
    assert created.json()["sender_device_id"] == observer["device_id"]
    assert created.json()["message_type"] == "TEXT"
    assert created.json()["text"] == "Нужна помощь на дороге"
    assert created.json()["delivered_at"] is None

    assert chats.status_code == 200
    assert chats.json()["chats"] == [
        {
            "observer_device_id": observer["device_id"],
            "last_message_id": created.json()["message_id"],
            "last_message_type": "TEXT",
            "last_text": "Нужна помощь на дороге",
            "last_created_at": created.json()["created_at"],
            "last_delivered_at": None,
        }
    ]

    assert messages.status_code == 200
    assert [message["message_id"] for message in messages.json()["messages"]] == [
        created.json()["message_id"]
    ]


def test_employee_answers_chat_and_marks_message_delivered_once(client):
    observer = register(client, "eyewitness", "c")
    chief = register(client, "employee", "d")

    first = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "Стою у обочины"},
    ).json()
    answer = client.post(
        "/api/v1/messages",
        headers=auth_headers(chief["access_token"], "employee"),
        json={
            "message_type": "TEXT",
            "observer_device_id": observer["device_id"],
            "text": "Инспектор выехал",
        },
    )
    delivered = client.patch(
        f"/api/v1/messages/{first['message_id']}/delivered",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    delivered_again = client.patch(
        f"/api/v1/messages/{first['message_id']}/delivered",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert answer.status_code == 200
    assert answer.json()["observer_device_id"] == observer["device_id"]
    assert answer.json()["sender_device_id"] == chief["device_id"]
    assert answer.json()["text"] == "Инспектор выехал"

    assert delivered.status_code == 200
    assert delivered.json()["delivered_at"] is not None
    assert delivered_again.status_code == 200
    assert delivered_again.json()["delivered_at"] == delivered.json()["delivered_at"]
    assert Message.select().count() == 2


def test_chat_messages_support_after_message_id(client):
    observer = register(client, "eyewitness", "e")
    chief = register(client, "employee", "f")

    first = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "Первое"},
    ).json()
    second = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "Второе"},
    ).json()

    response = client.get(
        f"/api/v1/chats/{observer['device_id']}/messages",
        headers=auth_headers(chief["access_token"], "employee"),
        params={"after_message_id": first["message_id"]},
    )

    assert response.status_code == 200
    assert [message["message_id"] for message in response.json()["messages"]] == [
        second["message_id"]
    ]


def test_employee_without_role_cannot_access_chats(client):
    register(client, "employee", "g")
    employee = register(client, "employee", "h")

    response = client.get(
        "/api/v1/chats",
        headers=auth_headers(employee["access_token"], "employee"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Chat access is not allowed for this device"


def test_eyewitness_cannot_access_another_chat(client):
    first = register(client, "eyewitness", "i")
    second = register(client, "eyewitness", "j")

    response = client.get(
        f"/api/v1/chats/{second['device_id']}/messages",
        headers=auth_headers(first["access_token"], "eyewitness"),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Eyewitness can only access own chat"
