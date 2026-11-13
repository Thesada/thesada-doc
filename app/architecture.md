---
title: Architecture
parent: Web App
nav_order: 1
description: "How thesada-app fits together: components, the telemetry and alert data flow, where state lives, and how it is deployed."
---

# Architecture

thesada-app is the Go web application at the centre of the platform. It ingests device telemetry from MQTT, persists it to Postgres/TimescaleDB, serves a web dashboard and a JSON API, and dispatches alerts. Firmware behaviour is documented under [Firmware]({{ site.baseurl }}/firmware/); this page covers the server side and how the pieces connect.

## Components

| Component | Repo | Language | What it owns |
|---|---|---|---|
| thesada-app | thesada-app | Go | Web dashboard (HTMX), JSON API (`/api/v1`), MQTT ingest, alerting, auth, the internal per-device certificate authority |
| Firmware | thesada-fw | C++ (ESP32) | Sensor reads, connectivity; publishes telemetry and alerts to MQTT, accepts config and command downlinks |
| MQTT broker | Mosquitto | C | Message bus for all device and app traffic; dynamic-security ACLs |
| Database | PostgreSQL + TimescaleDB | SQL | All platform state; a telemetry hypertable with continuous aggregates |
| Edge | Reverse proxy | - | Public TLS termination; MQTT TLS and mTLS ingress |

## Data flow

```mermaid
flowchart LR
  FW[Firmware] -- sensor --> B((MQTT broker))
  FW -- alert --> B
  B -- ingest --> APP[thesada-app]
  APP -- reading --> TS[(TimescaleDB<br/>telemetry)]
  APP -- alert --> PG[(Postgres<br/>device_alerts)]
  APP -- WebSocket --> UI[Browser dashboard]
  APP -- email / Telegram --> N[Notifier]
```

### Telemetry

1. Firmware publishes a reading to `<prefix>/sensor/<metric>` - a bare number, a string, or a `{ "value": ... }` object.
2. The app holds one wildcard MQTT subscription (QoS 1). On each message it taps the raw bytes (for the admin shell), parses tenant, device, and kind from the topic, and validates the tenant.
3. Sensor messages bump the device's `last_seen` and insert a row into the `device_telemetry` hypertable.
4. A WebSocket event fans out to every browser open on that tenant, so the dashboard updates live.

### Alerts

1. A Lua rule on the device publishes a JSON alert to `<prefix>/alert` (`severity` is `info`, `warn`, or `crit`, plus `code` and `message`). Malformed or unknown-severity payloads are dropped.
2. The app inserts the event into `device_alerts` and pushes a live WebSocket event.
3. A background dispatcher matches alert subscriptions - per device or tenant-wide, each with a minimum-severity threshold - and sends email and/or Telegram. Delivery flags are set idempotently so retries never double-send.
4. A failed send is retried with doubling backoff (a redispatch sweep also runs at startup, so a restart mid-alert loses nothing). After the attempt budget (default 5) the alert is dead-lettered and logged loudly; the attempt budget, backoff, and sweep cadence are configurable via `THESADA_ALERT_*` (see [Deploy]({{ site.baseurl }}/app/deploy.html)).

<!-- claim: repo=thesada-app ref=dev file=pkg/service/certificate.go match="ensureTenantSubscriptionTx\(ctx, tx, tenantID, devicePk\)" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="const DefaultSubscriptionSeverity = \"warn\"" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="ORDER BY \(d\.id IS NOT NULL\) DESC, u\.is_admin DESC, u\.is_super_admin, u\.created_at, u\.id" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="insertSubscriptionTx\(ctx, tx, userID, nil, channelID, DefaultSubscriptionSeverity\)" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="pg_advisory_xact_lock" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="sp, err := tx\.Begin\(ctx\)" why="savepoint, a failure only logs" -->
**Default subscription on pairing.** Pairing a device into a tenant that has no alert subscription yet creates one, so the first alerts reach someone. It goes to the user who claimed the device, else the oldest tenant admin, else the oldest user (super-admins last), covers all devices at `warn`, and sends to that user's account email. It runs on every pairing path (admin pair, the API pair and a self-service claim). Parallel or repeated pairings in one tenant create one subscription, and a failure here is logged as `alert.subscription.default_failed` and never undoes the pairing. A tenant that already has a subscription is left as it is.

<!-- claim: repo=thesada-app ref=dev file=pkg/web/templates/layout.html match="Nobody gets alerts for this tenant\." -->
<!-- claim: repo=thesada-app ref=dev file=pkg/web/web_device.go match="return paired && subs == 0" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/alert_default.go match="JOIN notification_channels c ON c\.id = s\.channel_id AND c\.enabled" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/web/templates/devices.html match="\{\{template \"alert-coverage\" \.\}\}" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/web/templates/alerts.html match="\{\{template \"alert-coverage\" \.\}\}" -->
**"Nobody gets alerts" banner.** While a tenant has a paired device and no user with a subscription on an enabled channel, the Devices and Alerts pages show `Nobody gets alerts for this tenant.` with a link to the notification settings. Alerts are still stored and shown, they just reach no one. The banner goes away once one subscription on an enabled channel exists.

## Where state lives

All persistent state is in PostgreSQL (with the TimescaleDB extension). Tenant isolation is enforced by Postgres row-level security (RLS) as the steady-state default: the app sets a per-transaction tenant identifier, so every query is automatically scoped to one tenant.

| Data | Store | Tenant isolation |
|---|---|---|
| Devices, users, sessions, API tokens | Postgres | RLS (direct column or via a foreign key) |
| Telemetry (raw readings) | TimescaleDB hypertable | application-enforced (see below) |
| Telemetry rollups | continuous aggregates (hourly, daily) | derived from telemetry |
| Alerts and subscriptions | Postgres | RLS via device / user foreign key |
| Device files and change history | Postgres | RLS |
| OAuth providers and identities | Postgres | RLS |
| Tenant registry | Postgres | none - cross-tenant by definition; read via an admin path or a slug cache |

**Telemetry is the one exception to RLS.** TimescaleDB rejects row-level security on a compression-enabled hypertable, so `device_telemetry` carries no policy. Isolation is enforced in the application instead: every telemetry read filters by `device_pk`, and a `device_pk` is only obtainable through a `devices` lookup that *is* RLS-scoped.

### Database roles

The app connects with three role-scoped pools:

| Pool | Role | Used for |
|---|---|---|
| App | tenant role, RLS enforced | the majority of reads and writes, scoped by the tenant identifier |
| Admin | bypass-RLS role | cross-tenant and pre-tenant work (migrations, session and token validation, aggregate refresh); every use is audit-logged |
| MQTT | ingest role | the telemetry subscriber, with narrow grants on its own connection budget |

## Deployment

The app, database, and broker run as one Docker Compose stack; CI builds and rolls it:

1. Build a versioned image, CVE-scan it (report-only), push to the registry.
2. Run database migrations in a one-shot container against the live database - a broken migration aborts here, with the old app still serving.
3. `docker compose up -d` swaps in the new image.
4. A healthcheck (`/api/v1/healthz`) and a login/redirect smoke test gate the release; on failure CI rolls back to the previous image automatically.

A TLS-terminating reverse proxy fronts the public endpoints. It terminates TLS for the web app, the OTA server, and the MQTT TLS port, and passes the MQTT mTLS port straight through so client certificates reach the broker.
