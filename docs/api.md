# API

Base URL:

```text
http://127.0.0.1:<port>
```

FastAPI also exposes generated docs:

```text
/docs
/openapi.json
```

## GET /health

Checks that the backend process is running.

Response 200:

```json
{
  "status": "ok"
}
```

## POST /api/v1/devices/register

Registers a physical device by `fingerprint_hash`.

Headers:

```http
X-Client-App: eyewitness
```

or:

```http
X-Client-App: employee
```

Request:

```json
{
  "fingerprint_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "push_token": null
}
```

Response 200:

```json
{
  "device_id": "uuid",
  "role": null,
  "access_token": "token"
}
```

For the first employee device, if there is no `CHIEF` yet:

```json
{
  "device_id": "uuid",
  "role": "CHIEF",
  "access_token": "token"
}
```

Notes:

- repeat registration by the same `fingerprint_hash` returns the same `device_id`;
- `access_token` is returned as plaintext only in this response;
- the database stores only `access_token_hash`;
- `X-Client-App` selects the scenario, but is not authorization.

## Employee Authorization

Protected employee endpoints require:

```http
Authorization: Bearer <access_token>
X-Client-App: employee
```

The backend finds the current `Device` by `access_token_hash`, then checks `devices.current_role`.

## GET /api/v1/employee/me

Returns the current authorized device.

Response 200:

```json
{
  "device_id": "uuid",
  "role": "CHIEF"
}
```

## GET /api/v1/employee/devices/{device_id}

Looks up a device after scanning QR.

Requires role manager rights:

- `ADMIN`
- `CHIEF`

Response 200:

```json
{
  "device_id": "uuid",
  "role": null
}
```

Response 404:

```json
{
  "detail": "Device not found"
}
```

## PUT /api/v1/employee/devices/{device_id}/role

Assigns or replaces a device role.

Request:

```json
{
  "role": "INSPECTOR"
}
```

Response 200 when a new role was assigned:

```json
{
  "device_id": "uuid",
  "role": "INSPECTOR",
  "event": {
    "action": "ASSIGNED"
  }
}
```

Response 200 when an existing role was replaced:

```json
{
  "device_id": "uuid",
  "role": "ADMIN",
  "event": {
    "action": "REPLACED"
  }
}
```

Response 200 when the role was already the same:

```json
{
  "device_id": "uuid",
  "role": "ADMIN",
  "event": null
}
```

Rights:

- `ADMIN` can assign `INSPECTOR`, `ADMIN`;
- `ADMIN` cannot assign `CHIEF`;
- `CHIEF` can assign `INSPECTOR`, `ADMIN`, `CHIEF`.

## DELETE /api/v1/employee/devices/{device_id}/role

Removes the current role.

Response 200:

```json
{
  "device_id": "uuid",
  "role": null,
  "event": {
    "action": "REMOVED"
  }
}
```

If the device already has no role, `event` is `null`.

