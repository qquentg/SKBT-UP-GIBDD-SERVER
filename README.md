# SKBT-UP-GIBDD-SERVER

Минимальный backend-срез для ИС "ГИБДД-Очевидец".

## Что уже есть

- `GET /health`
- `POST /api/v1/devices/register`
- Peewee-модели `devices`, `role_events`, `messages`, `media`, `static_locations`, `live_location_sessions`, `location_points`
- регистрация устройства по `fingerprint_hash`
- разделение сценариев через `X-Client-App: eyewitness|employee`
- автоматическое назначение первого `CHIEF` для employee-сценария
- запись `role_events.AUTO_ASSIGNED`
- несколько устройств с ролью `CHIEF` разрешены; ограничение "один CHIEF" действует только для автоматического bootstrap
- текстовые сообщения и список чатов по `messages.observer_device_id`
- статическая геолокация
- live-геолокация на 15 минут
- загрузка и скачивание медиа-файлов с TTL 7 дней

Не добавлены: WebSocket, bans, push, Excel, Docker.

## Требования

- Python 3.11+
- PostgreSQL

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Заполнить `.env` под свою отдельную PostgreSQL DB.

Создать таблицы:

```bash
python -m scripts.init_db
```

Пример запуска:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Проверка:

```bash
curl http://127.0.0.1:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

## Регистрация устройства

Eyewitness:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/devices/register \
  -H "Content-Type: application/json" \
  -H "X-Client-App: eyewitness" \
  -d '{"fingerprint_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
```

Employee:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/devices/register \
  -H "Content-Type: application/json" \
  -H "X-Client-App: employee" \
  -d '{"fingerprint_hash":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'
```

Если в БД еще нет `CHIEF`, первый employee-device получит:

```json
{"device_id":"...","role":"CHIEF"}
```

Повторная регистрация того же `fingerprint_hash` возвращает тот же `device_id`.

Bootstrap первого `CHIEF` в PostgreSQL защищен transaction advisory lock. Это нужно только для сценария автоматического назначения, чтобы два первых employee-запроса не получили `CHIEF` одновременно.

## PostgreSQL

Создать отдельную базу для своей реализации. Не использовать БД второго backend.

Пример:

```bash
sudo -u postgres psql
```

```sql
CREATE DATABASE gibdd_<your_name>;
CREATE USER gibdd_<your_name> WITH PASSWORD 'change_me';
GRANT ALL PRIVILEGES ON DATABASE gibdd_<your_name> TO gibdd_<your_name>;
```

Проверка подключения:

```bash
psql postgresql://gibdd_<your_name>:change_me@127.0.0.1:5432/gibdd_<your_name>
```

## Тесты

```bash
pytest
```

Тесты используют SQLite in-memory и проверяют первый рабочий сценарий без PostgreSQL.

## Поля

`devices.id`: внутренний UUID устройства. Нужен для QR, FK и API.

`devices.fingerprint_hash`: SHA-256 fingerprint устройства. Нужен, чтобы повторно вернуть тот же Device.

`devices.current_role`: текущая роль employee-устройства. Нужна для UI сотрудника и проверки прав.

`devices.push_token`: будущий адрес push-доставки. Сейчас сохраняется, но push не реализован.

`devices.last_activity_at`: время последней активности устройства.

`role_events`: история изменений ролей. Сейчас используется для `AUTO_ASSIGNED CHIEF`.

Для `AUTO_ASSIGNED` поле `actor_device_id` равно `NULL`, потому что роль назначает система, а не сотрудническое устройство.
