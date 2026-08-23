# API ГИБДД-Очевидец

Документ описывает API, которое уже реализовано в backend.

## Базовый адрес

Публичный тестовый сервер для APK:

```text
https://силенок.рф:4401
```

Для Retrofit/OkHttp base URL обычно нужно указывать со слешем в конце:

```text
https://силенок.рф:4401/
```

Если Android Studio, Gradle или HTTP-клиент плохо обрабатывает кириллический домен, можно использовать punycode-адрес. Это тот же самый домен:

```text
https://xn--e1afhclgq.xn--p1ai:4401/
```

API работает по HTTPS с обычным доверенным сертификатом Let's Encrypt. Для рабочего адреса не нужно включать `android:usesCleartextTraffic="true"`.

Для Android-приложения все равно нужно разрешение на интернет:

```xml
<uses-permission android:name="android.permission.INTERNET" />
```

Если в приложении раньше был включен cleartext только ради `http://193.124.115.164:4401`, после перехода на HTTPS это больше не требуется:

```xml
android:usesCleartextTraffic="true"  <!-- больше не нужно для https://силенок.рф:4401 -->
```

Если Retrofit настроен на старый адрес `http://193.124.115.164:4401/`, запросы после перехода на HTTPS могут не работать. Нужно использовать `https://силенок.рф:4401/`.

Если backend запущен на другом порту, меняется только базовый адрес. Пути эндпоинтов остаются такими же.

Публичный порт нашего backend API: `4401`. Второй backend может использовать другой порт, например `4402`.

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

Сейчас реализовано 23 эндпоинта:

```text
GET    /health
POST   /api/v1/devices/register
GET    /api/v1/devices/me/bans/active
GET    /api/v1/employee/me
GET    /api/v1/employee/devices
GET    /api/v1/employee/devices/{device_id}
PUT    /api/v1/employee/devices/{device_id}/role
DELETE /api/v1/employee/devices/{device_id}/role
POST   /api/v1/employee/devices/{device_id}/ban
GET    /api/v1/employee/devices/{device_id}/bans
GET    /api/v1/employee/devices/{device_id}/bans/active
POST   /api/v1/messages
POST   /api/v1/messages/static-location
POST   /api/v1/messages/media
POST   /api/v1/messages/media/upload
GET    /api/v1/messages/{message_id}/media
POST   /api/v1/messages/live-location/start
POST   /api/v1/messages/{message_id}/live-location/points
POST   /api/v1/messages/{message_id}/live-location/stop
GET    /api/v1/messages/{message_id}/live-location/points
GET    /api/v1/chats
GET    /api/v1/chats/{observer_device_id}/messages
PATCH  /api/v1/messages/{message_id}/delivered
```

## Формат даты и времени

Все поля времени приходят в ISO 8601.
Backend хранит и отдает время в UTC.

Примеры:

```json
{
  "created_at": "2026-08-23T12:30:15.123456Z",
  "last_created_at": "2026-08-23T12:30:15.123456Z",
  "started_at": "2026-08-23T12:00:00Z",
  "ends_at": "2026-08-24T12:00:00Z",
  "delivered_at": null
}
```

Для Android это можно парсить как `Instant`.
Если поле равно `null`, значит времени еще нет или срок бессрочный, например `ends_at: null` у постоянного бана.

## GET /health

Проверяет, что backend запущен.

Авторизация не нужна.

Пример запроса:

```bash
curl https://силенок.рф:4401/health
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
push_token       - необязательный FCM push-токен устройства, можно отправлять null
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
- `push_token` будет обновлен, если он передан в запросе.

Frontend должен заменить старый токен на новый.

Если приложение использует Firebase Cloud Messaging, Android должен получить FCM token и передать его в `push_token`.
Если FCM token обновился, нужно повторно вызвать регистрацию с тем же `fingerprint_hash` и новым `push_token`.

### Пример curl

```bash
curl -X POST https://силенок.рф:4401/api/v1/devices/register \
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
curl https://силенок.рф:4401/api/v1/employee/me \
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

## GET /api/v1/employee/devices

Возвращает список устройств сотрудников для экрана "Сотрудники".

Нужна авторизация сотрудника.

Доступ разрешен только ролям:

```text
ADMIN
CHIEF
```

Важно: в текущей ERD нет отдельного поля, по которому можно отличить employee-устройство без роли от устройства Очевидца.
Поэтому endpoint возвращает устройства, у которых уже есть employee-роль: `INSPECTOR`, `ADMIN` или `CHIEF`.

### Пример запроса

```bash
curl https://силенок.рф:4401/api/v1/employee/devices \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "devices": [
    {
      "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0002",
      "role": "CHIEF",
      "last_activity_at": "2026-08-23T12:30:15.123456Z"
    },
    {
      "device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003",
      "role": "INSPECTOR",
      "last_activity_at": "2026-08-23T12:35:00Z"
    }
  ]
}
```

Если текущий сотрудник не `ADMIN` и не `CHIEF`:

```json
{
  "detail": "Role management is not allowed for this device"
}
```

Статус: `403 Forbidden`.

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
curl https://силенок.рф:4401/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003 \
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
curl -X PUT https://силенок.рф:4401/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003/role \
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
curl -X DELETE https://силенок.рф:4401/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0003/role \
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

## POST /api/v1/employee/devices/{device_id}/ban

Блокирует Очевидца.

`device_id` здесь - это `device_id` Очевидца, чей чат блокируется.

Доступ:

```text
INSPECTOR
ADMIN
CHIEF
```

Уровень блокировки считается по истории банов этого Очевидца:

```text
1-й бан: 1 сутки
2-й бан: 30 дней
3-й бан и дальше: постоянный бан
```

В таблице `bans` не хранится `ban_number` или `ban_type`. Backend считает номер бана по истории.

Если у Очевидца уже есть активный бан, повторный запрос вернет текущий активный бан и не создаст новый.

### Пример запроса

```bash
curl -X POST https://силенок.рф:4401/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001/ban \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "ban_id": "8fdc98ed-fb31-41a6-b77e-6e12c26ec9a1",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "issued_by_device_id": "0f41d9ac-528b-4911-8a4c-b3546d32308c",
  "started_at": "2026-08-21T13:30:00Z",
  "ends_at": "2026-08-22T13:30:00Z",
  "ban_number": 1,
  "is_active": true
}
```

Для постоянного бана:

```json
{
  "ends_at": null
}
```

### Ошибки

```text
401 - нет токена или токен неправильный
403 - Ban is not allowed for this device
404 - Observer device not found
422 - device_id не UUID
```

## GET /api/v1/employee/devices/{device_id}/bans

Возвращает историю банов Очевидца.

Нужна роль:

```text
INSPECTOR
ADMIN
CHIEF
```

Пример:

```bash
curl https://силенок.рф:4401/api/v1/employee/devices/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001/bans \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

Ответ:

```json
{
  "bans": [
    {
      "ban_id": "8fdc98ed-fb31-41a6-b77e-6e12c26ec9a1",
      "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
      "issued_by_device_id": "0f41d9ac-528b-4911-8a4c-b3546d32308c",
      "started_at": "2026-08-21T13:30:00Z",
      "ends_at": "2026-08-22T13:30:00Z",
      "ban_number": 1,
      "is_active": true
    }
  ]
}
```

## GET /api/v1/employee/devices/{device_id}/bans/active

Возвращает активный бан Очевидца, если он есть.

Если активного бана нет:

```json
{
  "ban": null
}
```

Если активный бан есть:

```json
{
  "ban": {
    "ban_id": "8fdc98ed-fb31-41a6-b77e-6e12c26ec9a1",
    "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
    "issued_by_device_id": "0f41d9ac-528b-4911-8a4c-b3546d32308c",
    "started_at": "2026-08-21T13:30:00Z",
    "ends_at": "2026-08-22T13:30:00Z",
    "ban_number": 1,
    "is_active": true
  }
}
```

## GET /api/v1/devices/me/bans/active

Возвращает активный бан текущего Очевидца.

Этот endpoint нужен приложению Очевидца, чтобы показать срок блокировки на экране.

Нужны заголовки:

```http
Authorization: Bearer <access_token>
X-Client-App: eyewitness
```

Если активного бана нет:

```json
{
  "ban": null
}
```

Если активный бан есть:

```json
{
  "ban": {
    "ban_id": "8fdc98ed-fb31-41a6-b77e-6e12c26ec9a1",
    "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
    "issued_by_device_id": "0f41d9ac-528b-4911-8a4c-b3546d32308c",
    "started_at": "2026-08-23T12:00:00Z",
    "ends_at": "2026-08-24T12:00:00Z",
    "ban_number": 1,
    "is_active": true
  }
}
```

Если `ends_at` равен `null`, бан постоянный.

## Что меняется для забаненного Очевидца

Если Очевидец забанен, backend не удаляет его сообщения.
Сообщения, отправленные во время активного бана, сохраняются в БД, но видны только `CHIEF`.

Правило видимости заблокированных чатов:

```text
CHIEF             -> видит активный заблокированный чат и получает active_ban
ADMIN / INSPECTOR -> не видят активный заблокированный чат в GET /api/v1/chats
```

Когда бан закончился, новые сообщения снова видны `INSPECTOR`, `ADMIN` и `CHIEF`.
Сообщения, созданные во время периода бана, остаются скрытыми для `INSPECTOR` и `ADMIN`.

Если `ADMIN` или `INSPECTOR` напрямую запрашивает сообщения активного заблокированного чата:

```json
{
  "detail": "Banned chat is visible only to CHIEF"
}
```

Статус: `403 Forbidden`.

Статус блокировки также можно проверить отдельным endpoint:

```text
GET /api/v1/employee/devices/{observer_device_id}/bans/active
GET /api/v1/devices/me/bans/active
```

## POST /api/v1/messages

Создает текстовое сообщение.

Этот эндпоинт доступен и Очевидцу, и Сотруднику, но правила разные.

Очевидец пишет только в свой чат. Для него `observer_device_id` указывать не нужно: backend сам возьмет `device_id` текущего Очевидца.

Сотрудник пишет в чат конкретного Очевидца. Для него `observer_device_id` обязателен.

В текущем срезе реализован только тип:

```text
TEXT
STATIC_LOCATION
MEDIA
LIVE_LOCATION
```

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
  "static_location": null,
  "media": null,
  "live_location": null,
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

## POST /api/v1/messages/static-location

Создает сообщение со статической точкой на карте.

Это соответствует таблице `static_locations` из ERD.

Доступ:

```text
Очевидец  - отправляет точку в свой чат
Сотрудник - отправляет точку в чат конкретного Очевидца
```

Для Очевидца `observer_device_id` не нужен.

Для Сотрудника `observer_device_id` обязателен.

### Тело запроса от Очевидца

```json
{
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

### Тело запроса от Сотрудника

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

Ограничения:

```text
latitude  от -90 до 90
longitude от -180 до 180
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0002",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "STATIC_LOCATION",
  "text": null,
  "static_location": {
    "latitude": 55.7558,
    "longitude": 37.6173
  },
  "media": null,
  "live_location": null,
  "created_at": "2026-08-20T13:31:00Z",
  "delivered_at": null
}
```

## POST /api/v1/messages/media

Создает сообщение с медиа-файлом.

Это соответствует таблице `media` из ERD.

Сейчас backend не принимает сам файл. Он принимает метаданные уже сохраненного файла:

```text
storage_key - ключ/путь файла в хранилище
mime_type   - MIME-тип файла
```

Этот endpoint не принимает сам файл. Он нужен только для случая, когда файл уже сохранен в файловом хранилище backend, а backend получает готовый `storage_key`.

Backend проверяет, что файл по `storage_key` реально существует, MIME-тип поддерживается, а размер файла укладывается в ограничения. Если файла нет, сообщение не создается.

Если Android-приложение хочет отправить фото из `Uri`, нужно использовать `POST /api/v1/messages/media/upload`.

Доступ:

```text
Очевидец  - отправляет медиа в свой чат
Сотрудник - отправляет медиа в чат конкретного Очевидца
```

Для Очевидца `observer_device_id` не нужен.

Для Сотрудника `observer_device_id` обязателен.

### Тело запроса от Очевидца

```json
{
  "storage_key": "media/2026/08/photo.jpg",
  "mime_type": "image/jpeg"
}
```

### Тело запроса от Сотрудника

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "storage_key": "media/2026/08/photo.jpg",
  "mime_type": "image/jpeg"
}
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0003",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "MEDIA",
  "text": null,
  "static_location": null,
  "media": {
    "storage_key": "media/2026/08/photo.jpg",
    "mime_type": "image/jpeg",
    "last_viewed_at": null
  },
  "live_location": null,
  "created_at": "2026-08-20T13:32:00Z",
  "delivered_at": null
}
```

## POST /api/v1/messages/media/upload

Загружает сам файл на backend и создает сообщение типа `MEDIA`.

Это основной endpoint для Android, когда у приложения есть `Uri` фотографии или другого файла.

Формат запроса: `multipart/form-data`.

Заголовки:

```text
Authorization: Bearer <access_token>
X-Client-App: eyewitness
```

Поля формы:

```text
file - сам файл
```

Для Очевидца `observer_device_id` не нужен: сообщение попадет в его собственный чат.

Для Сотрудника нужно дополнительно передать:

```text
observer_device_id - device_id Очевидца, в чей чат отправляется файл
```

Поддерживаемые типы файлов:

```text
image/jpeg
image/png
image/webp
image/gif
video/mp4
```

Ограничения размера:

```text
Фото:     до 10 MB
GIF:      до 100 MB
Видео:    до 100 MB
```

Срок жизни медиа:

```text
7 дней с момента последнего скачивания мобильным клиентом.
Если файл ни разу не скачивали: 7 дней с момента отправки сообщения.
```

Истекшее медиа не скачивается. Старые файлы удаляются при обращении к ним и при следующих upload-запросах.

Пример через curl от Очевидца:

```bash
curl -X POST https://силенок.рф:4401/api/v1/messages/media/upload \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: eyewitness" \
  -F "file=@photo.jpg;type=image/jpeg"
```

Пример через curl от Сотрудника:

```bash
curl -X POST https://силенок.рф:4401/api/v1/messages/media/upload \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee" \
  -F "observer_device_id=2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001" \
  -F "file=@photo.jpg;type=image/jpeg"
```

Ответ такой же, как у `POST /api/v1/messages/media`.

В ответе поле `media.storage_key` возвращается для информации. Фронту не нужно самому формировать этот ключ при загрузке файла: backend создаст его автоматически.

Частые ошибки:

```text
400 - observer_device_id is required for employee messages
403 - нет доступа к чату
404 - Media file not found
413 - Media file is too large
415 - Unsupported media mime_type
422 - Media file cannot be empty
```

## GET /api/v1/messages/{message_id}/media

Возвращает файл медиа-сообщения.

Нужны те же заголовки авторизации:

```text
Authorization: Bearer <access_token>
X-Client-App: eyewitness или employee
```

Доступ:

```text
Очевидец  - может скачать медиа только из своего чата
Сотрудник - может скачать медиа из чатов, если у него есть роль INSPECTOR, ADMIN или CHIEF
```

Пример:

```bash
curl https://силенок.рф:4401/api/v1/messages/7d62ef94-d6ef-41de-ae37-5fb5bb2b0003/media \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee" \
  --output photo.jpg
```

Частые ошибки:

```text
400 - Message is not media
403 - нет доступа к чату
404 - Message not found
404 - Media file not found
410 - Media file has expired
```

## POST /api/v1/messages/live-location/start

Начинает live-трансляцию геолокации.

Это соответствует таблице `live_location_sessions` из ERD.

При старте backend создает сообщение:

```text
message_type = LIVE_LOCATION
```

и live-сессию:

```text
ends_at = текущее время + 15 минут
```

Доступ:

```text
Очевидец  - начинает трансляцию в своем чате
Сотрудник - начинает трансляцию в чате конкретного Очевидца
```

Для Очевидца `observer_device_id` не нужен.

Для Сотрудника `observer_device_id` обязателен.

### Тело запроса от Очевидца

```json
{}
```

### Тело запроса от Сотрудника

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001"
}
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0004",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "LIVE_LOCATION",
  "text": null,
  "static_location": null,
  "media": null,
  "live_location": {
    "ends_at": "2026-08-20T13:47:00Z"
  },
  "created_at": "2026-08-20T13:32:00Z",
  "delivered_at": null
}
```

## POST /api/v1/messages/{message_id}/live-location/points

Добавляет точку в live-трансляцию.

Это соответствует таблице `location_points` из ERD.

Точку может добавить только то устройство, которое начало эту live-трансляцию.

После `ends_at` новые точки не принимаются.

### Тело запроса

```json
{
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

Ограничения:

```text
latitude  от -90 до 90
longitude от -180 до 180
```

### Ответ

```json
{
  "recorded_at": "2026-08-20T13:33:00Z",
  "latitude": 55.7558,
  "longitude": 37.6173
}
```

Если трансляция уже завершена:

```json
{
  "detail": "Live location session has ended"
}
```

Статус: `403 Forbidden`.

Если точку пытается добавить не отправитель live-трансляции:

```json
{
  "detail": "Only live location sender can update this session"
}
```

Статус: `403 Forbidden`.

## POST /api/v1/messages/{message_id}/live-location/stop

Завершает live-трансляцию раньше 15 минут.

Завершить трансляцию может только то устройство, которое ее начало.

Backend ставит:

```text
ends_at = текущее время
```

### Ответ

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0004",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "LIVE_LOCATION",
  "text": null,
  "static_location": null,
  "media": null,
  "live_location": {
    "ends_at": "2026-08-20T13:35:00Z"
  },
  "created_at": "2026-08-20T13:32:00Z",
  "delivered_at": null
}
```

## GET /api/v1/messages/{message_id}/live-location/points

Возвращает точки live-трансляции.

Доступ:

```text
Очевидец  - только точки своего чата
Сотрудник - точки любого чата, если есть роль INSPECTOR / ADMIN / CHIEF
```

### Пример запроса

```bash
curl https://силенок.рф:4401/api/v1/messages/7d62ef94-d6ef-41de-ae37-5fb5bb2b0004/live-location/points \
  -H "Authorization: Bearer <access_token>" \
  -H "X-Client-App: employee"
```

### Ответ

```json
{
  "points": [
    {
      "recorded_at": "2026-08-20T13:33:00Z",
      "latitude": 55.7558,
      "longitude": 37.6173
    }
  ]
}
```

### Догрузка новых точек

Можно передать `after_recorded_at`, чтобы получить точки после уже сохраненной точки:

```text
GET /api/v1/messages/{message_id}/live-location/points?after_recorded_at=2026-08-20T13:33:00Z
```

Также есть параметр `limit`:

```text
GET /api/v1/messages/{message_id}/live-location/points?limit=100
```

Ограничения:

```text
limit минимум 1
limit максимум 300
по умолчанию 100
```

## GET /api/v1/chats

Возвращает список чатов для приложения Сотрудника.

В базе отдельной таблицы `chats` нет. Это вычисляемое представление по таблице `messages`, сгруппированное по `observer_device_id`.

Для каждого чата backend возвращает последнее сообщение и активный бан, если он есть.

Правило видимости заблокированных чатов:

```text
CHIEF             -> видит активные заблокированные чаты
ADMIN / INSPECTOR -> не видят активные заблокированные чаты
```

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
curl https://силенок.рф:4401/api/v1/chats \
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
      "last_static_location": null,
      "last_media": null,
      "last_live_location": null,
      "last_created_at": "2026-08-20T13:30:00Z",
      "last_delivered_at": null,
      "active_ban": null
    }
  ]
}
```

Если чат заблокирован и список запрашивает `CHIEF`, поле `active_ban` будет заполнено:

```json
{
  "chats": [
    {
      "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
      "last_message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
      "last_message_type": "TEXT",
      "last_text": "Нужна помощь на дороге",
      "last_static_location": null,
      "last_media": null,
      "last_live_location": null,
      "last_created_at": "2026-08-20T13:30:00Z",
      "last_delivered_at": null,
      "active_ban": {
        "ban_id": "8fdc98ed-fb31-41a6-b77e-6e12c26ec9a1",
        "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
        "issued_by_device_id": "9a7e4f5c-7f38-4f91-a9b0-3d0a68d5b01a",
        "started_at": "2026-08-21T13:30:00Z",
        "ends_at": "2026-08-22T13:30:00Z",
        "ban_number": 1,
        "is_active": true
      }
    }
  ]
}
```

Если последнее сообщение не текстовое, поля `last_*` заполняются по типу сообщения.

Пример для последнего фото:

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "last_message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0002",
  "last_message_type": "MEDIA",
  "last_text": null,
  "last_static_location": null,
  "last_media": {
    "storage_key": "2026/08/9a2f8c2e4b0d4a4e98f3a2d71d6e1c11.jpg",
    "mime_type": "image/jpeg",
    "last_viewed_at": null
  },
  "last_live_location": null,
  "last_created_at": "2026-08-23T12:31:00Z",
  "last_delivered_at": null,
  "active_ban": null
}
```

Пример для последней статической геолокации:

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "last_message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0004",
  "last_message_type": "STATIC_LOCATION",
  "last_text": null,
  "last_static_location": {
    "latitude": 55.7558,
    "longitude": 37.6173
  },
  "last_media": null,
  "last_live_location": null,
  "last_created_at": "2026-08-23T12:33:00Z",
  "last_delivered_at": null,
  "active_ban": null
}
```

Пример для последней live-геолокации:

```json
{
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "last_message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0005",
  "last_message_type": "LIVE_LOCATION",
  "last_text": null,
  "last_static_location": null,
  "last_media": null,
  "last_live_location": {
    "ends_at": "2026-08-23T12:48:00Z"
  },
  "last_created_at": "2026-08-23T12:33:00Z",
  "last_delivered_at": null,
  "active_ban": null
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
curl https://силенок.рф:4401/api/v1/chats/2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001/messages \
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
      "static_location": null,
      "media": null,
      "live_location": null,
      "created_at": "2026-08-20T13:30:00Z",
      "delivered_at": null
    }
  ]
}
```

### Примеры разных message_type

`TEXT`:

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0001",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "TEXT",
  "text": "Нужна помощь на дороге",
  "static_location": null,
  "media": null,
  "live_location": null,
  "created_at": "2026-08-23T12:30:15.123456Z",
  "delivered_at": null
}
```

`MEDIA`, фото:

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0002",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "MEDIA",
  "text": null,
  "static_location": null,
  "media": {
    "storage_key": "2026/08/9a2f8c2e4b0d4a4e98f3a2d71d6e1c11.jpg",
    "mime_type": "image/jpeg",
    "last_viewed_at": null
  },
  "live_location": null,
  "created_at": "2026-08-23T12:31:00Z",
  "delivered_at": null
}
```

`MEDIA`, видео:

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0003",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "MEDIA",
  "text": null,
  "static_location": null,
  "media": {
    "storage_key": "2026/08/20fa7d47693b45d2b5a0d823cb863581.mp4",
    "mime_type": "video/mp4",
    "last_viewed_at": null
  },
  "live_location": null,
  "created_at": "2026-08-23T12:32:00Z",
  "delivered_at": null
}
```

В ответе на сообщение с медиа нет прямого URL файла.
Файл нужно скачивать отдельным запросом:

```text
GET /api/v1/messages/{message_id}/media
```

`STATIC_LOCATION`:

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0004",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "STATIC_LOCATION",
  "text": null,
  "static_location": {
    "latitude": 55.7558,
    "longitude": 37.6173
  },
  "media": null,
  "live_location": null,
  "created_at": "2026-08-23T12:33:00Z",
  "delivered_at": null
}
```

`LIVE_LOCATION`:

```json
{
  "message_id": "7d62ef94-d6ef-41de-ae37-5fb5bb2b0005",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "LIVE_LOCATION",
  "text": null,
  "static_location": null,
  "media": null,
  "live_location": {
    "ends_at": "2026-08-23T12:48:00Z"
  },
  "created_at": "2026-08-23T12:33:00Z",
  "delivered_at": null
}
```

Координаты live-геолокации не лежат в самом сообщении.
Их нужно получать отдельно:

```text
GET /api/v1/messages/{message_id}/live-location/points
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
curl -X PATCH https://силенок.рф:4401/api/v1/messages/7d62ef94-d6ef-41de-ae37-5fb5bb2b0001/delivered \
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

## Push-уведомления

Отдельных endpoint'ов для push нет.

Frontend передает push-токен только в `POST /api/v1/devices/register`:

```json
{
  "fingerprint_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "push_token": "FCM_TOKEN_FROM_ANDROID"
}
```

Что делает backend:

- сохраняет `push_token` в `devices.push_token`;
- при повторной регистрации того же устройства обновляет `push_token`;
- при новом сообщении от Очевидца отправляет push всем employee-устройствам с ролью `INSPECTOR`, `ADMIN` или `CHIEF`, если у них есть `push_token`;
- при новом сообщении от забаненного Очевидца отправляет push только `CHIEF`;
- при новом сообщении от Сотрудника отправляет push Очевидцу, если у него есть `push_token`;
- при бане Очевидца отправляет push самому Очевидцу и другим `CHIEF`-устройствам;
- при старте live-геолокации отправляет один push о новом сообщении типа `LIVE_LOCATION`;
- при добавлении очередной точки live-геолокации push не отправляет, точки нужно получать через `GET /api/v1/messages/{message_id}/live-location/points`.

Push не заменяет REST API.
После открытия приложения frontend все равно должен получить актуальное состояние через обычные endpoint'ы: список чатов, сообщения, точки live-геолокации, статус бана.

Пример данных внутри push:

```json
{
  "event": "message_created",
  "message_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0004",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "sender_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "message_type": "TEXT"
}
```

Для бана:

```json
{
  "event": "observer_banned",
  "ban_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0005",
  "observer_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0001",
  "issued_by_device_id": "2b2c9f3c-1c9a-4b1f-b2f0-531f2b9b0002"
}
```

На сервере для реальной доставки через Firebase должны быть настроены переменные окружения:

```text
FCM_PROJECT_ID=<firebase_project_id>
FCM_SERVICE_ACCOUNT_FILE=/path/to/firebase-service-account.json
PUSH_REQUEST_TIMEOUT_SECONDS=3
```

Если эти переменные не настроены, backend продолжит сохранять `push_token` и работать с API, но внешняя отправка push в FCM будет пропущена.
Сами запросы создания сообщений и банов из-за ошибки push-доставки не падают.

## Быстрый сценарий для frontend

Минимальный порядок работы для приложения Сотрудника:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: employee`; если используется FCM, передать `push_token`.
2. Сохранить `device_id` и `access_token`.
3. Для защищенных запросов отправлять `Authorization: Bearer <access_token>`.
4. Чтобы узнать свою роль, вызвать `GET /api/v1/employee/me`.
5. Чтобы получить список сотрудников, вызвать `GET /api/v1/employee/devices`.
6. После сканирования QR другого устройства вызвать `GET /api/v1/employee/devices/{device_id}`.
7. Чтобы назначить роль, вызвать `PUT /api/v1/employee/devices/{device_id}/role`.
8. Чтобы удалить роль, вызвать `DELETE /api/v1/employee/devices/{device_id}/role`.
9. Чтобы получить список чатов, вызвать `GET /api/v1/chats`.
10. Чтобы открыть чат, вызвать `GET /api/v1/chats/{observer_device_id}/messages`.
11. Чтобы отправить текст в чат Очевидца, вызвать `POST /api/v1/messages` с `observer_device_id`.
12. Чтобы отправить точку в чат Очевидца, вызвать `POST /api/v1/messages/static-location` с `observer_device_id`.
13. Чтобы отправить файл в чат Очевидца, вызвать `POST /api/v1/messages/media/upload` с `observer_device_id`.
14. Чтобы заблокировать Очевидца, вызвать `POST /api/v1/employee/devices/{observer_device_id}/ban`.
15. Чтобы проверить активный бан, вызвать `GET /api/v1/employee/devices/{observer_device_id}/bans/active`.
16. Чтобы начать live-геолокацию в чате Очевидца, вызвать `POST /api/v1/messages/live-location/start` с `observer_device_id`.
17. Чтобы получить точки live-геолокации, вызвать `GET /api/v1/messages/{message_id}/live-location/points`.

Минимальный порядок работы для приложения Очевидца:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: eyewitness`; если используется FCM, передать `push_token`.
2. Сохранить `device_id` и `access_token`.
3. Чтобы проверить активный бан и его `ends_at`, вызвать `GET /api/v1/devices/me/bans/active`.
4. Чтобы отправить текстовое сообщение, вызвать `POST /api/v1/messages`.
5. Чтобы отправить точку, вызвать `POST /api/v1/messages/static-location`.
6. Чтобы отправить файл, вызвать `POST /api/v1/messages/media/upload`.
7. Чтобы начать live-геолокацию, вызвать `POST /api/v1/messages/live-location/start`.
8. Чтобы добавить точку live-геолокации, вызвать `POST /api/v1/messages/{message_id}/live-location/points`.
9. Чтобы завершить live-геолокацию, вызвать `POST /api/v1/messages/{message_id}/live-location/stop`.
10. Чтобы получить сообщения своего чата, вызвать `GET /api/v1/chats/{device_id}/messages`.
11. Чтобы отметить сообщение доставленным, вызвать `PATCH /api/v1/messages/{message_id}/delivered`.

## Что еще не реализовано

Эти части есть в общей схеме системы, но в текущем backend-срезе еще не сделаны:

```text
WebSocket / real-time события
```

Их не нужно использовать на фронте, пока для них не появятся отдельные эндпоинты.
