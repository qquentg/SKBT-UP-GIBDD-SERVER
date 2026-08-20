# API ГИБДД-Очевидец

Документ описывает API, которое уже реализовано в backend.

Писали простым языком для frontend-разработки, но технические детали здесь тоже важны: какие заголовки отправлять, какие поля ждать в ответе, какие ошибки возможны.

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

Сейчас реализовано 6 эндпоинтов:

```text
GET    /health
POST   /api/v1/devices/register
GET    /api/v1/employee/me
GET    /api/v1/employee/devices/{device_id}
PUT    /api/v1/employee/devices/{device_id}/role
DELETE /api/v1/employee/devices/{device_id}/role
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

## Быстрый сценарий для frontend

Минимальный порядок работы для приложения Сотрудника:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: employee`.
2. Сохранить `device_id` и `access_token`.
3. Для защищенных запросов отправлять `Authorization: Bearer <access_token>`.
4. Чтобы узнать свою роль, вызвать `GET /api/v1/employee/me`.
5. После сканирования QR другого устройства вызвать `GET /api/v1/employee/devices/{device_id}`.
6. Чтобы назначить роль, вызвать `PUT /api/v1/employee/devices/{device_id}/role`.
7. Чтобы удалить роль, вызвать `DELETE /api/v1/employee/devices/{device_id}/role`.

Минимальный порядок работы для приложения Очевидца:

1. При первом запуске вызвать `POST /api/v1/devices/register` с `X-Client-App: eyewitness`.
2. Сохранить `device_id` и `access_token`.
3. Пока других eyewitness-эндпоинтов в backend нет.

## Что еще не реализовано

Эти части есть в общей схеме системы, но в текущем backend-срезе еще не сделаны:

```text
сообщения
медиа
статическая геолокация
live-геолокация
список чатов
баны
push-уведомления
WebSocket / real-time события
```

Их не нужно использовать на фронте, пока для них не появятся отдельные эндпоинты.
