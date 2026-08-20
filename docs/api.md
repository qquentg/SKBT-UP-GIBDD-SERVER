# API ГИБДД-Очевидец

Документ описывает API, которое уже реализовано в backend.

## Базовый адрес

Публичный тестовый сервер для APK:

```text
http://193.124.115.164:4401
```

Локально:

```text
http://127.0.0.1:8001
```

Если backend запущен на другом порту, меняется только базовый адрес. Пути эндпоинтов остаются такими же.

Веб-порты `80` и `443` не используются для этого API, поэтому публичный тестовый порт backend: `4401`.

FastAPI также автоматически отдает интерактивную документацию:

```text
/docs
/openapi.json
```

## Общие правила

Все запросы и ответы используют JSON.

Для регистрации устройства обязательно нужен заголовок:

```http
X-Client-App: eyewitness
```

или:

```http
X-Client-App: employee
```

Значение означает, из какого приложения пришел запрос:

```text
eyewitness - приложение Очевидца
employee   - приложение Сотрудника
```

Для защищенных employee-запросов дополнительно нужен токен:

```http
Authorization: Bearer <access_token>
X-Client-App: employee
```

Важно:

- `X-Client-App` сам по себе не является авторизацией;
- права сотрудника определяются по `access_token`;
- `access_token` backend возвращает только при регистрации;
- при повторной регистрации того же `fingerprint_hash` вернется тот же `device_id`, но новый `access_token`;
- frontend должен сохранить последний полученный `access_token` и использовать именно его.

## Роли

В системе сейчас есть роли:

```text
null      - роли нет
INSPECTOR - Инспектор
ADMIN     - Администратор
CHIEF     - Начальник
```

Первый сотрудник, который зарегистрировался через приложение `employee`, автоматически получает роль `CHIEF`.

Следующие сотрудники автоматически роль не получают. Их должен назначить `ADMIN` или `CHIEF`.

`CHIEF` может быть несколько. Автоматически выдается только первый `CHIEF`.

## Список эндпоинтов

Сейчас реализовано 10 эндпоинтов:

```text
GET    /health
POST   /api/v1/devices/register
GET    /api/v1/employee/me
GET    /api/v1/employee/devices/{device_id}
PUT    /api/v1/employee/devices/{device_id}/role
DELETE /api/v1/employee/devices/{device_id}/role
POST   /api/v1/messages
GET    /api/v1/chats
GET    /api/v1/chats/{observer_device_id}/messages
PATCH  /api/v1/messages/{message_id}/delivered
```

## GET /health

Проверяет, что backend запущен.

Авторизация не нужна.

Пример запроса:

```bash
curl http://127.0.0.1:8001/health
```

Ответ `200 OK`:

```json
{
  "status": "ok"
}
```

## POST /api/v1/devices/register

Регистрирует устройство по `fingerprint_hash`.

Это главный первый запрос для обоих приложений: Очевидца и Сотрудника.

### Заголовки

Для Очевидца:

```http
X-Client-App: eyewitness
```

Для Сотрудника:

```http
X-Client-App: employee
```

### Тело запроса

```json
{
  "fingerprint_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "push_token": null
}
```

Поля:

```text
fingerprint_hash - обязательный хеш устройства, строка от 32 до 128 символов
push_token       - необязательный push-токен, можно отправлять null
```

### Ответ для Очевидца

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "role": null,
  "access_token": "plain-token-value"
}
```

У Очевидца роль обычно `null`.

### Ответ для первого Сотрудника

Если в системе еще нет ни одного `CHIEF`, первый сотрудник получает роль автоматически:

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0002",
  "role": "CHIEF",
  "access_token": "plain-token-value"
}
```

### Ответ для следующего Сотрудника

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": null,
  "access_token": "plain-token-value"
}
```

### Повторная регистрация

Если отправить тот же `fingerprint_hash` еще раз:

- `device_id` останется тем же;
- роль останется текущей;
- `access_token` будет новым.

Frontend должен заменить старый токен на новый.

### Пример curl

```bash
curl -X POST http://127.0.0.1:8001/api/v1/devices/register \
  -H "Content-Type: application/json" \
  -H "X-Client-App: employee" \
  -d "{\"fingerprint_hash\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"push_token\":null}"
```

### Возможные ошибки

Если не передать `X-Client-App` или передать неизвестное значение:

```json
{
  "detail": "..."
}
```

Статус будет `422 Unprocessable Entity`.

Если `fingerprint_hash` слишком короткий или слишком длинный, тоже будет `422`.

## Авторизация сотрудника

Все эндпоинты ниже относятся к приложению Сотрудника.

Для каждого запроса нужны заголовки:

```http
Authorization: Bearer <access_token>
X-Client-App: employee
```

Если токена нет:

```json
{
  "detail": "Authorization header is required"
}
```

Статус: `401 Unauthorized`.

Если заголовок есть, но формат неправильный:

```json
{
  "detail": "Bearer token is required"
}
```

Статус: `401 Unauthorized`.

Если токен неизвестный или старый:

```json
{
  "detail": "Invalid access token"
}
```

Статус: `401 Unauthorized`.

Если отправить employee-запрос с `X-Client-App: eyewitness`:

```json
{
  "detail": "Employee client is required"
}
```

Статус: `403 Forbidden`.

## GET /api/v1/employee/me

Возвращает информацию о текущем устройстве сотрудника.

Нужна авторизация сотрудника.

### Пример запроса

```bash
curl http://127.0.0.1:8001/api/v1/employee/me \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0002",
  "role": "CHIEF"
}
```

Если роли нет:

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": null
}
```

## GET /api/v1/employee/devices/{device_id}

Получает информацию о другом устройстве по `device_id`.

Практический сценарий: сотрудник сканирует QR-код другого устройства и frontend показывает, какая роль у этого устройства сейчас.

Нужна авторизация сотрудника.

Доступ разрешен только ролям:

```text
ADMIN
CHIEF
```

### Пример запроса

```bash
curl http://127.0.0.1:8001/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003 \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": null
}
```

### Ошибки

Если текущий сотрудник не `ADMIN` и не `CHIEF`:

```json
{
  "detail": "Role management is not allowed for this device"
}
```

Статус: `403 Forbidden`.

Если устройство не найдено:

```json
{
  "detail": "Device not found"
}
```

Статус: `404 Not Found`.

Если `device_id` не похож на UUID:

```json
{
  "detail": "..."
}
```

Статус: `422 Unprocessable Entity`.

## PUT /api/v1/employee/devices/{device_id}/role

Назначает или заменяет роль устройству.

Нужна авторизация сотрудника.

### Кто какие роли может назначать

`ADMIN` может назначить:

```text
INSPECTOR
ADMIN
```

`ADMIN` не может назначить:

```text
CHIEF
```

`CHIEF` может назначить:

```text
INSPECTOR
ADMIN
CHIEF
```

### Тело запроса

```json
{
  "role": "INSPECTOR"
}
```

Допустимые значения:

```text
INSPECTOR
ADMIN
CHIEF
```

### Пример запроса

```bash
curl -X PUT http://127.0.0.1:8001/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003/role \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee" \
  -d "{\"role\":\"INSPECTOR\"}"
```

### Ответ: роль назначена впервые

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": "INSPECTOR",
  "event": {
    "action": "ASSIGNED"
  }
}
```

### Ответ: роль заменена

Например, было `ADMIN`, стало `INSPECTOR`.

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": "INSPECTOR",
  "event": {
    "action": "REPLACED"
  }
}
```

### Ответ: такая роль уже была

Если назначить ту же самую роль повторно:

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": "INSPECTOR",
  "event": null
}
```

В этом случае новое событие в `role_events` не создается.

### Ошибки

Если текущий сотрудник не может управлять ролями:

```json
{
  "detail": "Role management is not allowed for this device"
}
```

Статус: `403 Forbidden`.

Если текущий сотрудник может управлять ролями, но не может назначить именно эту роль:

```json
{
  "detail": "This role cannot be assigned by the current device"
}
```

Статус: `403 Forbidden`.

Если устройство не найдено:

```json
{
  "detail": "Device not found"
}
```

Статус: `404 Not Found`.

Если роль указана неправильно:

```json
{
  "detail": "..."
}
```

Статус: `422 Unprocessable Entity`.

## DELETE /api/v1/employee/devices/{device_id}/role

Удаляет текущую роль у устройства.

После этого у устройства будет:

```json
{
  "role": null
}
```

Нужна авторизация сотрудника.

Удалять роли могут:

```text
ADMIN
CHIEF
```

### Пример запроса

```bash
curl -X DELETE http://127.0.0.1:8001/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003/role \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ: роль удалена

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": null,
  "event": {
    "action": "REMOVED"
  }
}
```

В `role_events.role` сохраняется та роль, которая была удалена.

### Ответ: роли и так не было

```json
{
  "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
  "role": null,
  "event": null
}
```

В этом случае новое событие в `role_events` не создается.

### Ошибки

Ошибки такие же, как у просмотра устройства:

```text
401 - нет токена или токен неправильный
403 - нет прав управлять ролями
404 - устройство не найдено
422 - device_id не UUID
```

## POST /api/v1/messages

Создает текстовое сообщение.

Этот эндпоинт доступен и Очевидцу, и Сотруднику, но правила разные.

Очевидец пишет только в свой чат. Для него `observer_device_id` указывать не нужно: backend сам возьмет `device_id` текущего Очевидца.

Сотрудник пишет в чат конкретного Очевидца. Для него `observer_device_id` обязателен.

В текущем срезе реализован только тип:

```text
TEXT
```

Типы `MEDIA`, `STATIC_LOCATION`, `LIVE_LOCATION` есть в ERD, но для них нужны отдельные таблицы и отдельные эндпоинты следующих срезов.

### Заголовки для Очевидца

```http
Authorization: Bearer <access_token>
X-Client-App: eyewitness
```

### Заголовки для Сотрудника

```http
Authorization: Bearer <access_token>
X-Client-App: employee
```

У Сотрудника должна быть одна из ролей:

```text
INSPECTOR
ADMIN
CHIEF
```

### Тело запроса от Очевидца

```json
{
  "message_type": "TEXT",
  "text": "Нужна помощь на дороге"
}
```

### Тело запроса от Сотрудника

```json
{
  "message_type": "TEXT",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "text": "Инспектор выехал"
}
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "TEXT",
  "text": "Нужна помощь на дороге",
  "created_at": "2026-08-20T13:30:00Z",
  "delivered_at": null
}
```

### Ошибки

Если текст пустой:

```json
{
  "detail": "Text message cannot be empty"
}
```

Статус: `422 Unprocessable Entity`.

Если Сотрудник отправляет сообщение без `observer_device_id`:

```json
{
  "detail": "observer_device_id is required for employee messages"
}
```

Статус: `400 Bad Request`.

Если у Сотрудника нет роли:

```json
{
  "detail": "Chat access is not allowed for this device"
}
```

Статус: `403 Forbidden`.

Если Очевидец пытается писать не в свой чат:

```json
{
  "detail": "Eyewitness can only write to own chat"
}
```

Статус: `403 Forbidden`.

## GET /api/v1/chats

Возвращает список чатов для приложения Сотрудника.

В базе отдельной таблицы `chats` нет. Это вычисляемое представление по таблице `messages`, сгруппированное по `observer_device_id`.

Для каждого чата backend возвращает последнее сообщение.

Нужна авторизация Сотрудника:

```http
Authorization: Bearer <access_token>
X-Client-App: employee
```

У Сотрудника должна быть одна из ролей:

```text
INSPECTOR
ADMIN
CHIEF
```

### Пример запроса

```bash
curl http://127.0.0.1:8001/api/v1/chats \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "chats": [
    {
      "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
      "last_message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
      "last_message_type": "TEXT",
      "last_text": "Нужна помощь на дороге",
      "last_created_at": "2026-08-20T13:30:00Z",
      "last_delivered_at": null
    }
  ]
}
```

Если сообщений еще нет:

```json
{
  "chats": []
}
```

## GET /api/v1/chats/{observer_device_id}/messages

Возвращает сообщения одного чата.

`observer_device_id` - это `device_id` Очевидца, вокруг которого сформирован чат.

Доступ:

```text
Очевидец  - только свой чат
Сотрудник - любой чат, если есть роль INSPECTOR / ADMIN / CHIEF
```

### Пример запроса

```bash
curl http://127.0.0.1:8001/api/v1/chats/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001/messages \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "messages": [
    {
      "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
      "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
      "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
      "message_type": "TEXT",
      "text": "Нужна помощь на дороге",
      "created_at": "2026-08-20T13:30:00Z",
      "delivered_at": null
    }
  ]
}
```

### Догрузка новых сообщений

Можно передать `after_message_id`, чтобы получить сообщения после уже сохраненного сообщения:

```text
GET /api/v1/chats/{observer_device_id}/messages?after_message_id=<message_id>
```

Также есть параметр `limit`:

```text
GET /api/v1/chats/{observer_device_id}/messages?limit=20
```

Ограничения:

```text
limit минимум 1
limit максимум 100
по умолчанию 50
```

### Ошибки

Если Очевидец пытается читать чужой чат:

```json
{
  "detail": "Eyewitness can only access own chat"
}
```

Статус: `403 Forbidden`.

Если чат привязан к несуществующему устройству:

```json
{
  "detail": "Observer device not found"
}
```

Статус: `404 Not Found`.

Если `after_message_id` относится к другому чату:

```json
{
  "detail": "after_message_id belongs to another chat"
}
```

Статус: `400 Bad Request`.

## PATCH /api/v1/messages/{message_id}/delivered

Отмечает сообщение как доставленное.

В ERD это поле:

```text
delivered_at
```

Логика:

```text
delivered_at = null      сообщение еще не отмечено доставленным
delivered_at заполнено  сообщение доставлено
```

Если вызвать эндпоинт повторно, дата доставки не изменится.

Доступ:

```text
Очевидец  - только сообщения своего чата
Сотрудник - сообщения любого чата, если есть роль INSPECTOR / ADMIN / CHIEF
```

### Пример запроса

```bash
curl -X PATCH http://127.0.0.1:8001/api/v1/messages/7d62ef94-d6ef-41de-ae37-5fb5bb2b0001/delivered \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "TEXT",
  "text": "Нужна помощь на дороге",
  "created_at": "2026-08-20T13:30:00Z",
  "delivered_at": "2026-08-20T13:30:05Z"
}
```

Если сообщение не найдено:

```json
{
  "detail": "Message not found"
}
```

Статус: `404 Not Found`.

## Быстрый сценарий для frontend

Минимальный порядок работы для приложения Сотрудника:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: employee`.
2. Сохранить `device_id` и `access_token`.
3. Для защищенных запросов отправлять `Authorization: Bearer <access_token>`.
4. Чтобы узнать свою роль, вызвать `GET /api/v1/employee/me`.
5. После сканирования QR другого устройства вызвать `GET /api/v1/employee/devices/{device_id}`.
6. Чтобы назначить роль, вызвать `PUT /api/v1/employee/devices/{device_id}/role`.
7. Чтобы удалить роль, вызвать `DELETE /api/v1/employee/devices/{device_id}/role`.
8. Чтобы получить список чатов, вызвать `GET /api/v1/chats`.
9. Чтобы открыть чат, вызвать `GET /api/v1/chats/{observer_device_id}/messages`.
10. Чтобы отправить текст в чат Очевидца, вызвать `POST /api/v1/messages` с `observer_device_id`.

Минимальный порядок работы для приложения Очевидца:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: eyewitness`.
2. Сохранить `device_id` и `access_token`.
3. Чтобы отправить текстовое сообщение, вызвать `POST /api/v1/messages`.
4. Чтобы получить сообщения своего чата, вызвать `GET /api/v1/chats/{device_id}/messages`.
5. Чтобы отметить сообщение доставленным, вызвать `PATCH /api/v1/messages/{message_id}/delivered`.

## Что еще не реализовано

Эти части есть в общей схеме системы, но в текущем backend-срезе еще не сделаны:

```text
медиа
статическая геолокация
live-геолокация
баны
push-уведомления
WebSocket / real-time события
```

Их не нужно использовать на фронте, пока для них не появятся отдельные эндпоинты.
