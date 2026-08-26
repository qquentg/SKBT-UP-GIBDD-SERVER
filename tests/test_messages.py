from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.core.config import get_settings
from app.models.live_location_session import LiveLocationSession
from app.models.location_point import LocationPoint
from app.models.media import Media
from app.models.message import Message
from app.models.static_location import StaticLocation
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
            "last_sender_device_id": observer["device_id"],
            "last_message_type": "TEXT",
            "last_text": "Нужна помощь на дороге",
            "last_static_location": None,
            "last_media": None,
            "last_live_location": None,
            "last_created_at": created.json()["created_at"],
            "last_delivered_at": None,
            "unread_count": 1,
            "active_ban": None,
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


def test_employee_own_undelivered_message_is_not_unread_in_chat_list(client):
    observer = register(client, "eyewitness", "A")
    chief = register(client, "employee", "B")

    answer = client.post(
        "/api/v1/messages",
        headers=auth_headers(chief["access_token"], "employee"),
        json={
            "message_type": "TEXT",
            "observer_device_id": observer["device_id"],
            "text": "Inspector is on the way",
        },
    )
    chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert answer.status_code == 200
    assert answer.json()["delivered_at"] is None

    assert chats.status_code == 200
    assert chats.json()["chats"][0]["last_message_id"] == answer.json()["message_id"]
    assert chats.json()["chats"][0]["last_sender_device_id"] == chief["device_id"]
    assert chats.json()["chats"][0]["last_delivered_at"] is None
    assert chats.json()["chats"][0]["unread_count"] == 0


def test_chat_list_unread_count_uses_observer_messages_only(client):
    observer = register(client, "eyewitness", "A")
    chief = register(client, "employee", "B")

    first = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "first"},
    ).json()
    second = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "TEXT", "text": "second"},
    ).json()
    client.patch(
        f"/api/v1/messages/{first['message_id']}/delivered",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert chats.status_code == 200
    assert chats.json()["chats"][0]["last_message_id"] == second["message_id"]
    assert chats.json()["chats"][0]["last_sender_device_id"] == observer["device_id"]
    assert chats.json()["chats"][0]["unread_count"] == 1


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


def test_eyewitness_sends_static_location_and_employee_reads_it(client):
    observer = register(client, "eyewitness", "k")
    chief = register(client, "employee", "l")

    created = client.post(
        "/api/v1/messages/static-location",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"latitude": 55.7558, "longitude": 37.6173},
    )
    messages = client.get(
        f"/api/v1/chats/{observer['device_id']}/messages",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert created.status_code == 200
    assert created.json()["message_type"] == "STATIC_LOCATION"
    assert created.json()["text"] is None
    assert created.json()["static_location"] == {
        "latitude": 55.7558,
        "longitude": 37.6173,
    }
    assert created.json()["media"] is None
    assert StaticLocation.select().count() == 1

    assert messages.status_code == 200
    assert messages.json()["messages"][0]["static_location"] == {
        "latitude": 55.7558,
        "longitude": 37.6173,
    }


def test_static_location_coordinates_are_validated(client):
    observer = register(client, "eyewitness", "m")

    bad_latitude = client.post(
        "/api/v1/messages/static-location",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"latitude": 91, "longitude": 37.6173},
    )
    bad_longitude = client.post(
        "/api/v1/messages/static-location",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"latitude": 55.7558, "longitude": 181},
    )

    assert bad_latitude.status_code == 422
    assert bad_longitude.status_code == 422


def test_employee_sends_media_to_observer_chat(client):
    observer = register(client, "eyewitness", "n")
    chief = register(client, "employee", "o")
    storage_key = "media/2026/08/photo.jpg"
    media_path = Path(get_settings().media_storage_dir) / storage_key
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_bytes(b"jpeg-bytes")

    created = client.post(
        "/api/v1/messages/media",
        headers=auth_headers(chief["access_token"], "employee"),
        json={
            "observer_device_id": observer["device_id"],
            "storage_key": storage_key,
            "mime_type": "image/jpeg",
        },
    )
    chats = client.get(
        "/api/v1/chats",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert created.status_code == 200
    assert created.json()["message_type"] == "MEDIA"
    assert created.json()["observer_device_id"] == observer["device_id"]
    assert created.json()["sender_device_id"] == chief["device_id"]
    assert created.json()["text"] is None
    assert created.json()["static_location"] is None
    assert created.json()["media"] == {
        "storage_key": storage_key,
        "mime_type": "image/jpeg",
        "last_viewed_at": None,
    }
    assert Media.select().count() == 1

    assert chats.status_code == 200
    assert chats.json()["chats"][0]["last_message_type"] == "MEDIA"
    assert chats.json()["chats"][0]["last_media"]["storage_key"] == storage_key


def test_media_metadata_endpoint_requires_existing_file(client):
    observer = register(client, "eyewitness", "z")

    created = client.post(
        "/api/v1/messages/media",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={
            "storage_key": "media/missing.jpg",
            "mime_type": "image/jpeg",
        },
    )

    assert created.status_code == 404
    assert created.json()["detail"] == "Media file not found"


def test_eyewitness_uploads_media_file_and_employee_downloads_it(client):
    observer = register(client, "eyewitness", "v")
    chief = register(client, "employee", "w")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
    )
    downloaded = client.get(
        f"/api/v1/messages/{created.json()['message_id']}/media",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert created.status_code == 200
    assert created.json()["message_type"] == "MEDIA"
    assert created.json()["observer_device_id"] == observer["device_id"]
    assert created.json()["sender_device_id"] == observer["device_id"]
    assert created.json()["media"]["mime_type"] == "image/jpeg"
    assert created.json()["media"]["storage_key"].endswith(".jpg")
    assert Media.select().count() == 1

    assert downloaded.status_code == 200
    assert downloaded.content == b"jpeg-bytes"
    assert downloaded.headers["content-type"] == "image/jpeg"
    media = Media.get()
    assert media.last_viewed_at is not None


def test_employee_uploads_media_file_to_observer_chat(client):
    observer = register(client, "eyewitness", "x")
    chief = register(client, "employee", "y")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(chief["access_token"], "employee"),
        data={"observer_device_id": observer["device_id"]},
        files={"file": ("answer.png", b"png-bytes", "image/png")},
    )

    assert created.status_code == 200
    assert created.json()["message_type"] == "MEDIA"
    assert created.json()["observer_device_id"] == observer["device_id"]
    assert created.json()["sender_device_id"] == chief["device_id"]
    assert created.json()["media"]["mime_type"] == "image/png"
    assert created.json()["media"]["storage_key"].endswith(".png")


def test_media_download_requires_chat_access(client):
    observer = register(client, "eyewitness", "0")
    other_observer = register(client, "eyewitness", "1")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
    )
    downloaded = client.get(
        f"/api/v1/messages/{created.json()['message_id']}/media",
        headers=auth_headers(other_observer["access_token"], "eyewitness"),
    )

    assert downloaded.status_code == 403
    assert downloaded.json()["detail"] == "Eyewitness can only access own chat"


def test_empty_media_upload_is_rejected(client):
    observer = register(client, "eyewitness", "2")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )

    assert created.status_code == 422
    assert created.json()["detail"] == "Media file cannot be empty"


def test_expired_media_file_is_not_downloaded(client):
    observer = register(client, "eyewitness", "6")
    chief = register(client, "employee", "7")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
    ).json()
    media = Media.get()
    media_path = Path(get_settings().media_storage_dir) / media.storage_key
    Message.update(created_at=datetime.now(UTC) - timedelta(days=8)).where(
        Message.id == created["message_id"]
    ).execute()

    downloaded = client.get(
        f"/api/v1/messages/{created['message_id']}/media",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert downloaded.status_code == 410
    assert downloaded.json()["detail"] == "Media file has expired"
    assert not media_path.exists()


def test_recent_media_view_extends_ttl(client):
    observer = register(client, "eyewitness", "8")
    chief = register(client, "employee", "9")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("photo.jpg", b"jpeg-bytes", "image/jpeg")},
    ).json()
    Message.update(created_at=datetime.now(UTC) - timedelta(days=8)).where(
        Message.id == created["message_id"]
    ).execute()
    Media.update(last_viewed_at=utc_now()).where(
        Media.message == created["message_id"]
    ).execute()

    downloaded = client.get(
        f"/api/v1/messages/{created['message_id']}/media",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert downloaded.status_code == 200
    assert downloaded.content == b"jpeg-bytes"


def test_media_upload_cleans_expired_files(client):
    observer = register(client, "eyewitness", "!")

    old_message = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("old.jpg", b"old-bytes", "image/jpeg")},
    ).json()
    old_media = Media.get()
    old_media_path = Path(get_settings().media_storage_dir) / old_media.storage_key
    Message.update(created_at=datetime.now(UTC) - timedelta(days=8)).where(
        Message.id == old_message["message_id"]
    ).execute()

    new_message = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("new.jpg", b"new-bytes", "image/jpeg")},
    )

    assert new_message.status_code == 200
    assert not old_media_path.exists()


def test_unsupported_media_mime_type_is_rejected(client):
    observer = register(client, "eyewitness", "3")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("document.pdf", b"pdf-bytes", "application/pdf")},
    )

    assert created.status_code == 415
    assert created.json()["detail"] == "Unsupported media mime_type"


def test_photo_upload_limit_is_10_mb(client):
    observer = register(client, "eyewitness", "4")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("too-large.jpg", b"x" * (10 * 1024 * 1024 + 1), "image/jpeg")},
    )

    assert created.status_code == 413
    assert created.json()["detail"] == "Media file is too large"


def test_gif_upload_can_be_larger_than_photo_limit(client):
    observer = register(client, "eyewitness", "5")

    created = client.post(
        "/api/v1/messages/media/upload",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        files={"file": ("animation.gif", b"x" * (10 * 1024 * 1024 + 1), "image/gif")},
    )

    assert created.status_code == 200
    assert created.json()["media"]["mime_type"] == "image/gif"


def test_common_message_endpoint_accepts_only_text(client):
    observer = register(client, "eyewitness", "p")

    response = client.post(
        "/api/v1/messages",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"message_type": "MEDIA", "text": "wrong endpoint"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Use dedicated endpoint for this message_type"


def test_eyewitness_starts_live_location_and_employee_reads_points(client):
    observer = register(client, "eyewitness", "q")
    chief = register(client, "employee", "r")

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
    points = client.get(
        f"/api/v1/messages/{started.json()['message_id']}/live-location/points",
        headers=auth_headers(chief["access_token"], "employee"),
    )
    messages = client.get(
        f"/api/v1/chats/{observer['device_id']}/messages",
        headers=auth_headers(chief["access_token"], "employee"),
    )

    assert started.status_code == 200
    assert started.json()["message_type"] == "LIVE_LOCATION"
    assert started.json()["live_location"]["ends_at"] is not None
    assert LiveLocationSession.select().count() == 1

    assert point.status_code == 200
    assert point.json()["latitude"] == 55.7558
    assert point.json()["longitude"] == 37.6173
    assert LocationPoint.select().count() == 1

    assert points.status_code == 200
    assert points.json()["points"] == [point.json()]

    assert messages.status_code == 200
    assert messages.json()["messages"][0]["message_type"] == "LIVE_LOCATION"
    assert messages.json()["messages"][0]["live_location"]["ends_at"] == (
        started.json()["live_location"]["ends_at"]
    )


def test_live_location_stop_prevents_new_points(client):
    observer = register(client, "eyewitness", "s")

    started = client.post(
        "/api/v1/messages/live-location/start",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={},
    ).json()
    stopped = client.post(
        f"/api/v1/messages/{started['message_id']}/live-location/stop",
        headers=auth_headers(observer["access_token"], "eyewitness"),
    )
    point_after_stop = client.post(
        f"/api/v1/messages/{started['message_id']}/live-location/points",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={"latitude": 55.7558, "longitude": 37.6173},
    )

    assert stopped.status_code == 200
    stopped_at = datetime.fromisoformat(
        stopped.json()["live_location"]["ends_at"].replace("Z", "+00:00")
    )
    original_ends_at = datetime.fromisoformat(
        started["live_location"]["ends_at"].replace("Z", "+00:00")
    )
    assert stopped_at < original_ends_at
    assert point_after_stop.status_code == 403
    assert point_after_stop.json()["detail"] == "Live location session has ended"


def test_only_live_location_sender_can_add_points(client):
    observer = register(client, "eyewitness", "t")
    chief = register(client, "employee", "u")

    started = client.post(
        "/api/v1/messages/live-location/start",
        headers=auth_headers(observer["access_token"], "eyewitness"),
        json={},
    ).json()

    response = client.post(
        f"/api/v1/messages/{started['message_id']}/live-location/points",
        headers=auth_headers(chief["access_token"], "employee"),
        json={"latitude": 55.7558, "longitude": 37.6173},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Only live location sender can update this session"
