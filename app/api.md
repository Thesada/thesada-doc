---
title: API
parent: Web App
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
| 400 | malformed request - bad id, invalid JSON body, or invalid field value |
| 401 | no valid credential presented |
| 403 | authenticated but missing the required role (e.g. a non-super-admin calling pair) |
| 404 | resource not found, or outside your tenant |

On the unauthenticated enrollment endpoints, 403 means something else: one uniform refusal covering every reason a device enrollment did not proceed. See [Device enrollment](#device-enrollment).

## Errors

Every error response is a JSON object with a single `error` string:

```json
{ "error": "device not found" }
```

Success bodies vary by endpoint (an object, an array, or `{ "status": "ok" }`).

## List limits

List endpoints accept `?limit=` - default **100**, maximum **500**. Out-of-range or unparseable values fall back to the default.

## Endpoints

| Method | Path | Auth | OK | Purpose |
|---|---|---|---|---|
| GET | `/healthz` | none | 200 | liveness probe |
| GET | `/readyz` | none | 200 / 503 | readiness probe (DB + broker) |
| GET | `/version` | none | 200 | running CalVer, commit, and build time |
| POST | `/auth/login` | none | 200 | password login - returns a bearer token + user |
| POST | `/auth/logout` | optional | 200 | revoke the presented token and/or cookie |
| POST | `/auth/signup` | none | 200 | join the waitlist |
| GET | `/devices` | yes | 200 | list the tenant's devices |
| GET | `/devices/{id}` | yes | 200 | one device |
| POST | `/devices/{id}/pair` | super-admin | 200 | issue a device client certificate |
| POST | `/devices/enroll` | none | 200 | device announces itself, gets a challenge |
| POST | `/devices/enroll/verify` | none | 200 | device returns a signature over the challenge |
| POST | `/devices/enroll/cert` | none | 200 / 204 | device collects its certificate once claimed |
| POST | `/devices/enroll/ack` | none | 200 | device confirms the certificate is stored |
| GET | `/devices/{id}/telemetry` | yes | 200 | telemetry readings |
| GET | `/devices/{id}/alerts` | yes | 200 | a device's alerts |
| GET | `/alerts` | yes | 200 | the tenant's alerts |
| GET | `/alert-subscriptions` | yes | 200 | the caller's alert subscriptions |
| POST | `/alert-subscriptions` | yes | 201 | create a subscription |
| DELETE | `/alert-subscriptions/{id}` | yes | 204 | delete a subscription |

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

### Device enrollment

The four `/devices/enroll*` endpoints are the only unauthenticated device-facing surface in the API. A factory-fresh device has no credential to authenticate with, so these are guarded by rate limits, a claim token, and an Ed25519 proof of key possession instead. The narrative version of the flow is in [Provisioning]({{ site.baseurl }}/app/provisioning.html#self-service-enrollment).

Every refusal on this surface is the same 403 with the same body, whatever went wrong:

```json
{ "error": "enrollment refused" }
```

Unknown device id, wrong claim token, stale or already-consumed challenge, bad signature, an already-redeemed enrollment and a spent rate-limit bucket are indistinguishable to the caller. That is deliberate: device ids are derived from sequentially assigned factory MACs, so a caller who guesses one must not be able to tell a real id from a fabricated one. The detail goes to the server log, not the response.

Rate limits, spent before anything else is judged:

| Scope | Budget | Applies to |
|---|---|---|
| client IP | 60/hour | all four endpoints |
| (`device_id`, `pubkey`) | 30/hour | all four endpoints |
| `device_id` alone | 30/hour | announce only - the endpoint that creates rows |

Request bodies are capped at 4096 bytes. The client IP is taken from `X-Forwarded-For` only when the peer is inside `THESADA_TRUSTED_PROXIES`, otherwise from the connection itself.

**POST /devices/enroll** - body `{ "device_id": ..., "pubkey": ..., "claim_token": ... }`. `pubkey` is the device's Ed25519 public key as lowercase hex; `claim_token` is the plaintext claim token (the device's setup portal will surface it once the firmware enrollment client ships - the endpoints on this page are live today). Returns a fresh challenge to sign:

```json
{ "challenge": "<64 hex chars>", "expires_in": 300 }
```

Any well-formed `device_id` and `pubkey` get a challenge, always, whatever state the enrollment is in - refusing here would answer the one question this surface must not answer, which ids are real. Re-announcing is expected and replaces the outstanding challenge, so an old one cannot be answered later. The claim token may rotate on re-announce, but only until the enrollment is verified; after that the stored token stands and the change is ignored silently.

**POST /devices/enroll/verify** - body `{ "device_id": ..., "pubkey": ..., "signature": ... }`. `signature` is the Ed25519 signature over the challenge bytes, hex-encoded. Returns `{ "status": "verified" }`.

Every endpoint after announce names its row by (`device_id`, `pubkey`) - that pair is the row's identity, and a claim token never selects a row. The signature proves the caller holds the row's private key. The challenge is consumed whether or not the signature checks out, so a failed attempt burns the nonce rather than leaving it grindable for the rest of its five minutes.

**POST /devices/enroll/cert** - body `{ "device_id": ..., "pubkey": ..., "claim_token": ... }`. The claim token must additionally match the row - the pubkey is public, so the primary key alone is not a credential. Three outcomes:

| Status | Meaning |
|---|---|
| 200 | claimed - the certificate bundle is in the body |
| 204 | verified but nobody has claimed the device yet; keep polling |
| 403 | anything else |

```json
{
  "cert_pem": "-----BEGIN CERTIFICATE----- ...",
  "key_pem": "-----BEGIN PRIVATE KEY----- ...",
  "tenant": "<tenant slug>",
  "device_id": "thesada-0123456789ab",
  "topic_prefix": "<root>/<tenant>/<device-id>",
  "mqtt_host": "<broker host>",
  "mqtt_port": 8884
}
```

The tenant, topic prefix, broker host and mTLS port travel with the certificate because without them the device holds a credential it cannot use: the CN, the broker ACL and the app's ingest are all keyed on the tenant, and the firmware's default topic prefix belongs to no tenant.

There is no `ca_pem`. That would be the private device CA the broker uses to verify client certificates; the device verifies the broker against public roots it already carries, and handing it the device CA invites it to overwrite its own trust anchor and lose MQTT and OTA.

**POST /devices/enroll/ack** - body `{ "device_id": ..., "pubkey": ..., "claim_token": ... }`. Returns `{ "status": "sealed" }`, and is idempotent - a second call on an already-sealed enrollment answers the same way.

The certificate endpoint does not seal the enrollment; this does. Until the acknowledgement lands, `/devices/enroll/cert` re-issues, which is what makes delivery safe to retry when a device dies between receiving a certificate and storing it. Once sealed, the enrollment is terminal: a second delivery needs an explicit re-pair, so a leaked claim token cannot be redeemed twice.

### Alerts and subscriptions

**GET /alerts** - the tenant's recent alerts (newest first), bounded by `?limit=`.

**GET /alert-subscriptions** - the calling user's subscriptions.

**POST /alert-subscriptions** - body:

```json
{ "channel": "email", "min_severity": "warn", "device_pk": null }
```

`channel` is `email` or `telegram`. `min_severity` is `info`, `warn`, or `crit` (default `warn`). `device_pk` is optional - omit it or send `null` to cover all of the user's devices; a supplied id must belong to your tenant. Returns 201 `{ "status": "created" }`.

**DELETE /alert-subscriptions/{id}** - removes one of your subscriptions. Idempotent; returns 204.
