---
title: API
parent: App
nav_order: 5
description: "The /api/v1 JSON REST API: authentication, devices, telemetry, alerts, and alert subscriptions."
---

# API

thesada-app serves a versioned JSON REST API at `/api/v1`. The web dashboard and the client apps use the same contract. All request and response bodies are JSON.

## Authentication

Most endpoints require authentication. Two credentials are accepted:

- **Bearer token** - `Authorization: Bearer <token>`. Obtain one from `POST /auth/login`.
- **Session cookie** - set by the same login; used by web-origin clients.

Tokens and session tokens are stored only as SHA-256 hashes server-side.

| Status | Meaning |
|---|---|
| 401 | no valid credential presented |
| 403 | authenticated but missing the required role (e.g. a non-super-admin calling pair) |

## Errors

Every error response is a JSON object with a single `error` string:

```json
{ "error": "device not found" }
```

Success bodies vary by endpoint (an object, an array, or `{ "status": "ok" }`).

## List limits

List endpoints accept `?limit=` - default **100**, maximum **500**. Out-of-range or unparseable values fall back to the default.

## Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/healthz` | none | liveness probe |
| POST | `/auth/login` | none | password login - returns a bearer token + user |
| POST | `/auth/logout` | optional | revoke the presented token and/or cookie |
| POST | `/auth/signup` | none | join the waitlist |
| GET | `/devices` | yes | list the tenant's devices |
| GET | `/devices/{id}` | yes | one device |
| POST | `/devices/{id}/pair` | super-admin | issue a device client certificate |
| GET | `/devices/{id}/telemetry` | yes | telemetry readings |
| GET | `/devices/{id}/alerts` | yes | a device's alerts |
| GET | `/alerts` | yes | the tenant's alerts |
| GET | `/alert-subscriptions` | yes | the caller's alert subscriptions |
| POST | `/alert-subscriptions` | yes | create a subscription |
| DELETE | `/alert-subscriptions/{id}` | yes | delete a subscription |

`POST /auth/magic-link` is reserved and not yet available.

### Auth

**POST /auth/login** - body `{ "email": ..., "password": ... }`. On success returns the bearer token, its expiry, and the redacted user, and also sets the session cookie. Bad credentials return 401.

```json
{
  "token": "<bearer token>",
  "expires_at": "2026-06-22T18:00:00Z",
  "user": {
    "id": "<uuid>",
    "email": "you@example.com",
    "display_name": "You",
    "tenant_id": "default",
    "is_admin": false,
    "is_super_admin": false
  }
}
```

**POST /auth/logout** - revokes whichever credential you present (bearer and/or cookie) and clears the cookie. Idempotent; returns `{ "status": "ok" }`.

**POST /auth/signup** - body `{ "email": ..., "note": "<optional>" }`. Always returns `{ "status": "ok" }` - it never reveals whether an email is already known.

### Devices

**GET /devices** returns an array of the caller tenant's devices. **GET /devices/{id}** returns one (404 if it is not in your tenant). Device shape:

```json
{
  "id": "<uuid>",
  "device_id": "<factory id>",
  "display_name": "Boiler node",
  "hardware_type": "esp32-owb",
  "firmware_version": "1.5.0",
  "paired_at": "...",
  "last_seen_at": "...",
  "created_at": "...",
  "last_uptime_seconds": 86400,
  "last_uptime_at": "..."
}
```

**POST /devices/{id}/pair** (super-admin) issues and stores a new client certificate for the device and returns it. The private key is returned once and is never stored server-side.

```json
{
  "cn": "thesada-<tenant>-<device>",
  "serial_hex": "...",
  "not_before": "...",
  "not_after": "...",
  "cert_pem": "-----BEGIN CERTIFICATE----- ...",
  "private_key_pem": "-----BEGIN PRIVATE KEY----- ...",
  "ca_pem": "-----BEGIN CERTIFICATE----- ..."
}
```

**GET /devices/{id}/telemetry** - with no parameters, the latest reading per metric. With `?metric=<name>`, the recent readings of that single metric (newest first), bounded by `?limit=`. Reading shape:

```json
{ "metric": "temp.boiler", "received_at": "...", "value_num": 72.5, "value_text": null }
```

**GET /devices/{id}/alerts** - a device's alerts, newest first. Optional `?severity=info|warn|crit` filter and `?limit=`. Alert shape:

```json
{ "id": 1234, "received_at": "...", "severity": "warn", "code": "battery_low",
  "message": "Battery low for 60 s", "delivered_email": true, "delivered_telegram": false }
```

### Alerts and subscriptions

**GET /alerts** - the tenant's recent alerts (newest first), bounded by `?limit=`.

**GET /alert-subscriptions** - the calling user's subscriptions.

**POST /alert-subscriptions** - body:

```json
{ "channel": "email", "min_severity": "warn", "device_pk": null }
```

`channel` is `email` or `telegram`. `min_severity` is `info`, `warn`, or `crit` (default `warn`). `device_pk` is optional - omit it or send `null` to cover all of the user's devices; a supplied id must belong to your tenant. Returns 201 `{ "status": "created" }`.

**DELETE /alert-subscriptions/{id}** - removes one of your subscriptions. Idempotent; returns 204.
