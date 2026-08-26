from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from html import escape
import secrets
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import Depends, FastAPI, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.core.config import get_settings
from app.db.database import close_database, connect_database, database_proxy, init_database
from app.models.device import Device, utc_now
from app.models.live_location_session import LiveLocationSession
from app.models.location_point import LocationPoint
from app.models.media import Media
from app.models.message import Message
from app.models.role_event import RoleEvent
from app.models.static_location import StaticLocation
from app.schemas.device import DeviceRole, RoleAction

security = HTTPBasic()


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    connect_database()
    try:
        yield
    finally:
        close_database()


app = FastAPI(
    title="GIBDD temporary admin panel",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> None:
    password = get_settings().admin_panel_password
    if not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_PANEL_PASSWORD is not configured",
        )

    password_ok = secrets.compare_digest(credentials.password, password)
    user_ok = secrets.compare_digest(credentials.username, "admin")
    if not (user_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )


@app.get("/", response_class=HTMLResponse)
def index(
    _: None = Depends(require_admin),
    message: str | None = None,
    error: str | None = None,
) -> str:
    since = utc_now() - timedelta(hours=24)
    devices = list(Device.select().order_by(Device.last_activity_at.desc()))
    messages = list(
        Message.select()
        .where(Message.created_at >= since)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(200)
    )
    media_rows = list_recent_media(since)
    stats = collect_stats(since)

    return render_page(
        devices=devices,
        messages=messages,
        media_rows=media_rows,
        stats=stats,
        message=message,
        error=error,
    )


@app.post("/devices/{device_id}/role")
def update_device_role(
    device_id: UUID,
    _: None = Depends(require_admin),
    role: Annotated[str, Form()] = "",
) -> RedirectResponse:
    target = Device.get_or_none(Device.id == device_id)
    if target is None:
        return redirect(error="Device not found")

    normalized_role = role.strip().upper()
    if normalized_role == "":
        new_role = None
    elif normalized_role in {item.value for item in DeviceRole}:
        new_role = normalized_role
    else:
        return redirect(error="Invalid role")

    old_role = target.current_role
    if old_role == new_role:
        return redirect(message="Role is unchanged")

    with database_proxy.atomic():
        Device.update(current_role=new_role, last_activity_at=utc_now()).where(
            Device.id == target.id
        ).execute()
        RoleEvent.create(
            actor_device=None,
            target_device=target.id,
            action=role_action(old_role=old_role, new_role=new_role).value,
            role=new_role or old_role,
        )

    return redirect(message=f"Role updated for {target.id}")


def role_action(*, old_role: str | None, new_role: str | None) -> RoleAction:
    if new_role is None:
        return RoleAction.REMOVED
    if old_role is None:
        return RoleAction.ASSIGNED
    return RoleAction.REPLACED


def redirect(*, message: str | None = None, error: str | None = None) -> RedirectResponse:
    query = ""
    if message is not None:
        query = f"?message={quote(message)}"
    if error is not None:
        query = f"?error={quote(error)}"
    return RedirectResponse(url=f"/{query}", status_code=status.HTTP_303_SEE_OTHER)


def list_recent_media(since: datetime) -> list[tuple[Media, Message]]:
    rows: list[tuple[Media, Message]] = []
    query = (
        Media.select(Media, Message)
        .join(Message)
        .where(Message.created_at >= since)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(100)
    )
    for media in query:
        rows.append((media, media.message))
    return rows


def collect_stats(since: datetime) -> dict[str, object]:
    messages = list(Message.select().where(Message.created_at >= since))
    total_devices = Device.select().count()
    devices_with_push = Device.select().where(Device.push_token.is_null(False)).count()
    active_devices = Device.select().where(Device.last_activity_at >= since).count()
    roles = {
        "NO_ROLE": Device.select().where(Device.current_role.is_null()).count(),
        "INSPECTOR": Device.select().where(Device.current_role == "INSPECTOR").count(),
        "ADMIN": Device.select().where(Device.current_role == "ADMIN").count(),
        "CHIEF": Device.select().where(Device.current_role == "CHIEF").count(),
    }
    message_types: dict[str, int] = {}
    for message in messages:
        message_types[message.message_type] = message_types.get(message.message_type, 0) + 1

    return {
        "total_devices": total_devices,
        "active_devices_24h": active_devices,
        "devices_with_push": devices_with_push,
        "roles": roles,
        "messages_24h": len(messages),
        "message_types_24h": message_types,
        "media_24h": len(list_recent_media(since)),
        "static_locations_24h": count_related_messages(StaticLocation, since),
        "live_sessions_24h": count_related_messages(LiveLocationSession, since),
        "live_points_24h": LocationPoint.select()
        .where(LocationPoint.recorded_at >= since)
        .count(),
    }


def count_related_messages(model, since: datetime) -> int:
    return (
        model.select(model, Message)
        .join(Message)
        .where(Message.created_at >= since)
        .count()
    )


def render_page(
    *,
    devices: list[Device],
    messages: list[Message],
    media_rows: list[tuple[Media, Message]],
    stats: dict[str, object],
    message: str | None,
    error: str | None,
) -> str:
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ГИБДД-Очевидец admin</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f3f6fb;
      --panel: #ffffff;
      --line: #d7deea;
      --line-soft: #edf1f7;
      --text: #111827;
      --muted: #64748b;
      --accent: #155eef;
      --accent-soft: #eff4ff;
      --danger: #b42318;
      --ok: #067647;
      --shadow: 0 12px 30px rgba(15, 23, 42, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Arial, sans-serif; background: var(--bg); color: var(--text); }}
    header {{ padding: 22px 28px; background: linear-gradient(135deg, #10213f, #1d4ed8); color: #fff; box-shadow: var(--shadow); }}
    .topbar {{ display: flex; justify-content: space-between; gap: 16px; align-items: center; max-width: 1480px; margin: 0 auto; }}
    h1 {{ margin: 0; font-size: 24px; line-height: 1.2; }}
    .pill {{ display: inline-flex; align-items: center; min-height: 28px; padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.22); font-size: 13px; white-space: nowrap; }}
    main {{ max-width: 1480px; margin: 0 auto; padding: 22px 28px 44px; }}
    section {{ margin: 0 0 24px; }}
    .section-head {{ display: flex; justify-content: space-between; gap: 12px; align-items: end; margin-bottom: 10px; }}
    h2 {{ margin: 0; font-size: 19px; line-height: 1.25; }}
    .section-note {{ color: var(--muted); font-size: 13px; }}
    .notice {{ padding: 10px 12px; margin-bottom: 16px; border-radius: 6px; background: #ecfdf3; color: var(--ok); border: 1px solid #abefc6; }}
    .error {{ padding: 10px 12px; margin-bottom: 16px; border-radius: 6px; background: #fef3f2; color: var(--danger); border: 1px solid #fecdca; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }}
    .stat {{ background: var(--panel); border: 1px solid var(--line-soft); border-radius: 10px; padding: 14px; box-shadow: 0 6px 16px rgba(15,23,42,.04); }}
    .stat span {{ display: block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; }}
    .stat b {{ display: block; font-size: 26px; line-height: 1.1; margin-top: 7px; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 12px; }}
    .meta-card {{ background: var(--panel); border: 1px solid var(--line-soft); border-radius: 10px; padding: 14px; }}
    .meta-title {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 10px; }}
    .badges {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .badge {{ display: inline-flex; gap: 6px; align-items: center; min-height: 26px; padding: 4px 9px; border-radius: 999px; background: var(--accent-soft); color: #1849a9; font-size: 12px; font-weight: 700; }}
    .table-wrap {{ overflow-x: auto; background: var(--panel); border: 1px solid var(--line); border-radius: 10px; box-shadow: 0 8px 22px rgba(15,23,42,.05); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 900px; }}
    th, td {{ padding: 10px 11px; border-bottom: 1px solid var(--line-soft); text-align: left; vertical-align: top; font-size: 13px; }}
    th {{ background: #f8fafc; color: #475467; font-size: 12px; text-transform: uppercase; letter-spacing: .03em; position: sticky; top: 0; }}
    tr:hover td {{ background: #fbfdff; }}
    code {{ font-family: Consolas, monospace; font-size: 12px; background: #f8fafc; border: 1px solid var(--line-soft); border-radius: 5px; padding: 2px 4px; }}
    .muted {{ color: var(--muted); }}
    form {{ display: flex; gap: 8px; align-items: center; }}
    select, button {{ height: 34px; border: 1px solid var(--line); border-radius: 7px; background: #fff; }}
    select {{ min-width: 122px; padding: 0 8px; }}
    button {{ padding: 0 13px; background: var(--accent); color: #fff; border-color: var(--accent); cursor: pointer; font-weight: 700; }}
    button:hover {{ background: #004eeb; }}
    .role {{ font-weight: 700; }}
    .role-tag {{ display: inline-flex; min-height: 24px; align-items: center; padding: 3px 8px; border-radius: 999px; background: #eef2ff; color: #3538cd; font-size: 12px; font-weight: 700; }}
    .role-empty {{ background: #f2f4f7; color: #475467; }}
    @media (max-width: 720px) {{
      header {{ padding: 18px; }}
      .topbar {{ align-items: flex-start; flex-direction: column; }}
      main {{ padding: 18px; }}
      .section-head {{ align-items: flex-start; flex-direction: column; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <h1>ГИБДД-Очевидец: админ-панель</h1>
      <div class="pill">порт 4411</div>
    </div>
  </header>
  <main>
    {render_flash(message=message, error=error)}
    <section>
      <div class="section-head">
        <h2>Статистика</h2>
        <div class="section-note">Сводка по базе и активности за последние 24 часа</div>
      </div>
      {render_stats(stats)}
    </section>
    <section>
      <div class="section-head">
        <h2>Устройства и роли</h2>
        <div class="section-note">Выдача, замена и снятие роли у конкретного device_id</div>
      </div>
      {render_devices(devices)}
    </section>
    <section>
      <div class="section-head">
        <h2>Сообщения за последние 24 часа</h2>
        <div class="section-note">Последние 200 записей</div>
      </div>
      {render_messages(messages)}
    </section>
    <section>
      <div class="section-head">
        <h2>Медиа за последние 24 часа</h2>
        <div class="section-note">Последние 100 файлов</div>
      </div>
      {render_media(media_rows)}
    </section>
  </main>
</body>
</html>"""


def render_flash(*, message: str | None, error: str | None) -> str:
    if error:
        return f'<div class="error">{escape(error)}</div>'
    if message:
        return f'<div class="notice">{escape(message)}</div>'
    return ""


def render_stats(stats: dict[str, object]) -> str:
    roles = stats["roles"]
    message_types = stats["message_types_24h"]
    role_badges = render_badges(roles)
    message_type_badges = render_badges(message_types)
    return f"""
<div class="grid">
  <div class="stat"><span>Всего устройств</span><b>{stats["total_devices"]}</b></div>
  <div class="stat"><span>Активны за 24ч</span><b>{stats["active_devices_24h"]}</b></div>
  <div class="stat"><span>С push token</span><b>{stats["devices_with_push"]}</b></div>
  <div class="stat"><span>Сообщения за 24ч</span><b>{stats["messages_24h"]}</b></div>
  <div class="stat"><span>Медиа за 24ч</span><b>{stats["media_24h"]}</b></div>
  <div class="stat"><span>Статическая гео за 24ч</span><b>{stats["static_locations_24h"]}</b></div>
  <div class="stat"><span>Live-сессии за 24ч</span><b>{stats["live_sessions_24h"]}</b></div>
  <div class="stat"><span>Live-точки за 24ч</span><b>{stats["live_points_24h"]}</b></div>
</div>
<div class="meta-grid">
  <div class="meta-card"><div class="meta-title">Роли</div><div class="badges">{role_badges}</div></div>
  <div class="meta-card"><div class="meta-title">Типы сообщений за 24ч</div><div class="badges">{message_type_badges}</div></div>
</div>"""


def render_devices(devices: list[Device]) -> str:
    rows = []
    for device in devices:
        rows.append(
            f"""<tr>
  <td><code>{escape(str(device.id))}</code></td>
  <td><code>{escape(short_hash(device.fingerprint_hash))}</code></td>
  <td class="role">{role_tag(device.current_role)}</td>
  <td>{yes_no(bool(device.push_token))}</td>
  <td>{fmt_dt(device.last_activity_at)}</td>
  <td>{render_role_form(device)}</td>
</tr>"""
        )
    return table(
        headers=["device_id", "fingerprint", "role", "push", "last_activity", "change"],
        rows=rows,
    )


def render_role_form(device: Device) -> str:
    options = [("", "NO_ROLE"), ("INSPECTOR", "INSPECTOR"), ("ADMIN", "ADMIN"), ("CHIEF", "CHIEF")]
    option_html = "".join(
        f'<option value="{escape(value)}"{" selected" if (device.current_role or "") == value else ""}>{escape(label)}</option>'
        for value, label in options
    )
    return f"""
<form method="post" action="/devices/{device.id}/role">
  <select name="role">{option_html}</select>
  <button type="submit">Сохранить</button>
</form>"""


def role_tag(role: str | None) -> str:
    value = role or "NO_ROLE"
    extra_class = " role-empty" if role is None else ""
    return f'<span class="role-tag{extra_class}">{escape(value)}</span>'


def render_badges(values: object) -> str:
    if not isinstance(values, dict) or not values:
        return '<span class="muted">Нет данных</span>'
    return "".join(
        f'<span class="badge">{escape(str(key))}: {escape(str(value))}</span>'
        for key, value in values.items()
    )


def render_messages(messages: list[Message]) -> str:
    rows = []
    for message in messages:
        rows.append(
            f"""<tr>
  <td>{fmt_dt(message.created_at)}</td>
  <td><code>{escape(str(message.id))}</code></td>
  <td>{escape(message.message_type)}</td>
  <td><code>{escape(str(message.observer_device_id))}</code></td>
  <td><code>{escape(str(message.sender_device_id))}</code></td>
  <td>{fmt_dt(message.delivered_at)}</td>
  <td>{escape((message.text or "")[:120])}</td>
</tr>"""
        )
    return table(
        headers=["created", "message_id", "type", "observer", "sender", "delivered", "text"],
        rows=rows,
    )


def render_media(media_rows: list[tuple[Media, Message]]) -> str:
    rows = []
    for media, message in media_rows:
        rows.append(
            f"""<tr>
  <td>{fmt_dt(message.created_at)}</td>
  <td><code>{escape(str(message.id))}</code></td>
  <td>{escape(media.mime_type)}</td>
  <td><code>{escape(media.storage_key)}</code></td>
  <td>{fmt_dt(media.last_viewed_at)}</td>
  <td><code>{escape(str(message.observer_device_id))}</code></td>
  <td><code>{escape(str(message.sender_device_id))}</code></td>
</tr>"""
        )
    return table(
        headers=["created", "message_id", "mime", "storage_key", "last_viewed", "observer", "sender"],
        rows=rows,
    )


def table(*, headers: list[str], rows: list[str]) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    body_html = "\n".join(rows) if rows else f'<tr><td colspan="{len(headers)}" class="muted">Нет данных</td></tr>'
    return f'<div class="table-wrap"><table><thead><tr>{header_html}</tr></thead><tbody>{body_html}</tbody></table></div>'


def short_hash(value: str) -> str:
    return value if len(value) <= 18 else f"{value[:10]}...{value[-6:]}"


def yes_no(value: bool) -> str:
    return "yes" if value else "no"


def fmt_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return escape(value.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC"))
