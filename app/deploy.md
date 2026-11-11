---
title: Deployment
parent: Web App
nav_order: 4
description: "Self-host thesada-app: the standalone binary or the Docker Compose stack, the one-shot migration job, and the configuration it needs."
---

# Deployment

thesada-app is a single static Go binary with its templates, CSS, and SQL migrations embedded, so there is no asset directory to ship and nothing to compile at runtime. It needs a PostgreSQL database with the TimescaleDB extension and an MQTT broker. There are two ways to run it.

| Path | Best for | Brings its own DB + broker |
|---|---|---|
| [Docker Compose](#docker-compose-full-stack) | a turnkey stack on one host | yes |
| [Standalone binary](#standalone-binary) | running against infrastructure you already have | no |

## Docker Compose (full stack)

The `deploy/` directory ships a Compose stack (app + TimescaleDB + MQTT broker) and a bootstrap script.

```sh
cd deploy
./startup.sh
```

`startup.sh` is idempotent. On a first run it:

1. Copies `app.env.example` to `app.env` and `db.env.example` to `db.env`.
2. Generates the database password, `THESADA_COOKIE_SECRET`, and the CA key passphrase, and writes them into those files (mode `0600`).
3. Pulls the images, runs the database migrations as a one-shot, and starts the stack.

The app then listens on `http://127.0.0.1:8080`. Put a TLS reverse proxy in front of it before exposing it to anything.

Finish configuration by editing `app.env`:

- `THESADA_ADMIN_EMAIL` - the first super-admin. On boot a one-shot login link for that user is written to the app log (`docker compose logs app`).
- `THESADA_SMTP_*` - outbound mail for magic-link and password-reset email. With `THESADA_SMTP_HOST` empty the link is logged instead of sent.
- `THESADA_BASE_URL` - the public URL clients reach, used to build email links.

Re-run `docker compose up -d` after editing.

> The bundled broker config is plaintext on the internal Compose network only. Before exposing the broker, harden it with TLS and per-device mTLS - see [Provisioning]({{ site.baseurl }}/app/provisioning.html) for the certificate model.

## Standalone binary

Download the `thesada-app` binary from the GitHub Releases page and run it against your own PostgreSQL 14+/TimescaleDB and MQTT broker.

```sh
# 1. apply migrations (one-shot, exits when done)
THESADA_DATABASE_URL=postgres://user:pass@db:5432/thesada_app ./thesada-app migrate

# 2. run the server
THESADA_DATABASE_URL=postgres://user:pass@db:5432/thesada_app \
THESADA_MQTT_URL=mqtt://broker:1883 \
THESADA_COOKIE_SECRET=$(openssl rand -hex 32) \
./thesada-app
```

The binary is `linux/amd64`, statically linked (`CGO_ENABLED=0`), and carries no runtime dependencies. The full set of environment variables is below; `app.env.example` in the repo is the annotated reference.

## Subcommands

The binary takes an optional subcommand as its first argument. Both are one-shot - they do their work and exit before any server starts.

| Subcommand | What it does |
|---|---|
| `migrate` | apply pending schema migrations, then exit (0 on success, 1 on failure) |
| `ca-encrypt` | rewrite the on-disk CA key from plaintext PEM to an AES-256-GCM envelope using `THESADA_CA_KEY_PASSPHRASE`; leaves a `.plaintext.bak`; idempotent |

With no subcommand the binary starts the long-running server.

### Migrations

`migrate` runs separately from the server, never on server boot.

| Property | Behaviour |
|---|---|
| Tracking | `schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ)`, created `IF NOT EXISTS`; versions tracked by file basename |
| Idempotent | already-applied versions are skipped; each insert is `ON CONFLICT (version) DO NOTHING` |
| Transactions | each file runs in its own transaction; the version row is inserted in the same transaction as the DDL |
| Order | a failed migration aborts before the new server starts, leaving the prior version serving |

<!-- claim: repo=thesada-app ref=dev file=migrations/0040_device_broker_identity.sql match="SET LOCAL ROLE thesada_app_admin;" -->
<!-- claim: repo=thesada-app ref=dev file=migrations/0041_cert_pubkey_backfill_rls.sql match="Needs: GRANT thesada_app_admin TO thesada_app" -->
<!-- claim: repo=thesada-app ref=dev file=docs/runbook.md match="permission denied to set role" -->
<!-- claim: repo=thesada-app ref=dev file=docs/runbook.md match="`thesada-app migrate` runs as `thesada_app`, the owner of every table" -->
Tenant tables enforce row-level security even for their owner, so a migration that changes rows in one switches to the bypass-RLS admin role with `SET LOCAL ROLE thesada_app_admin`. From migration 0040 on, the role `migrate` connects as (`thesada_app`, the owner of every table) needs a one-time grant, run as a superuser before the first such `migrate`:

```sql
GRANT thesada_app_admin TO thesada_app;
```

Without it, 0040 fails with `permission denied to set role "thesada_app_admin"`, the migration aborts, and the prior version keeps serving. Grant, then run `migrate` again.

<!-- claim: repo=thesada-app ref=dev file=migrations/0001_init.sql match="IF NOT EXISTS \(SELECT 1 FROM pg_roles WHERE rolname = 'thesada_app_admin'\) THEN\n        CREATE ROLE thesada_app_admin BYPASSRLS NOLOGIN;" -->
<!-- claim: repo=thesada-app ref=dev file=migrations/0001_init.sql match="ALTER ROLE thesada_app_admin LOGIN;" -->
<!-- claim: repo=thesada-app ref=dev file=deploy/docker-compose.yml match="POSTGRES_USER: thesada_app\n" -->
**On a fresh database** the role `thesada_app_admin` does not exist until migration 0001 creates it, so the grant cannot run first. What to do depends on whether `thesada_app` is a superuser:

| Setup | `thesada_app` | Before the first `migrate` |
|---|---|---|
| `deploy/docker-compose.yml` (`startup.sh`) | `POSTGRES_USER`, which the image makes a superuser | nothing. 0001 creates the roles, and a superuser may `SET ROLE` to any role |
| Separate superuser, `thesada_app` a plain owner role (the hardened setup) | not a superuser, cannot create a `BYPASSRLS` role or make it `LOGIN`, and does not own `public` on PostgreSQL 15+ | run the bootstrap below as the superuser |

<!-- claim: repo=thesada-app ref=dev file=migrations/0001_init.sql match="ALTER MATERIALIZED VIEW device_telemetry_hourly OWNER TO thesada_app_admin;" -->
<!-- claim: repo=thesada-app ref=dev file=migrations/0001_init.sql match="GRANT CONNECT ON DATABASE thesada_app TO thesada_app_admin, thesada_app_mqtt;" -->
<!-- claim: repo=thesada-app ref=dev file=migrations/0001_init.sql match="SELECT create_hypertable\(" absent="CREATE EXTENSION[^;]*timescaledb" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/servicetest/postgres.go match="Image = \"timescale/timescaledb:[0-9.]+-pg17\"" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/servicetest/postgres.go match="ALTER DATABASE `\+dbName\+` OWNER TO thesada_app;\n\s*ALTER SCHEMA public OWNER TO thesada_app;\n\s*GRANT ALL ON SCHEMA public TO thesada_app;\n\s*GRANT thesada_app_admin TO thesada_app;\n\s*GRANT USAGE, CREATE ON SCHEMA public TO thesada_app_admin;" -->
<!-- claim: repo=thesada-app ref=dev file=pkg/service/servicetest/postgres.go match="GRANT USAGE, CREATE ON SCHEMA _timescaledb_internal TO thesada_app_admin;" -->
<!-- claim: repo=thesada-app ref=dev file=migrations/migrate_integration_test.go match="servicetest\.BootstrapProdRoles\(t, super\)\n\s*migrator := servicetest\.OpenAs\(t, baseURL, \"thesada_app\"\)" -->
The database has to be named `thesada_app`, because 0001 grants `CONNECT` on that name. Run this as the superuser, connected to that database, before the first `migrate`:

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE ROLE thesada_app       LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE ROLE thesada_app_admin LOGIN NOSUPERUSER BYPASSRLS   NOCREATEDB NOCREATEROLE;
CREATE ROLE thesada_app_mqtt  LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;

ALTER DATABASE thesada_app OWNER TO thesada_app;
ALTER SCHEMA public OWNER TO thesada_app;
GRANT ALL ON SCHEMA public TO thesada_app;

GRANT thesada_app_admin TO thesada_app;
GRANT USAGE, CREATE ON SCHEMA public TO thesada_app_admin;
GRANT USAGE, CREATE ON SCHEMA _timescaledb_internal TO thesada_app_admin;
```

Set a password on each role whose pool connects with one (`ALTER ROLE ... PASSWORD`). What each line is for:

| Statement | Why |
|---|---|
| `CREATE EXTENSION timescaledb` | 0001 calls `create_hypertable` but never creates the extension, and a plain role cannot. It also creates `_timescaledb_internal`, which the last grant needs |
| the three roles | 0001 skips a role that already exists, and a plain role cannot create a `BYPASSRLS` role or make it `LOGIN`. `LOGIN` on `thesada_app_admin` is the state 0001 leaves it in: the TimescaleDB refresh worker needs it |
| `thesada_app` owns the database and `public` | PostgreSQL 15 and later no longer grant `CREATE` on `public` to every role, and `migrate` creates every table as `thesada_app` |
| `GRANT thesada_app_admin TO thesada_app` | `migrate` can `SET LOCAL ROLE thesada_app_admin` (0040 on) and hand objects to that role |
| `CREATE` on `public` for `thesada_app_admin` | 0001 makes `thesada_app_admin` the owner of the two continuous aggregates. PostgreSQL lets a non-superuser hand an object to a new owner only when that owner has `CREATE` on the object's schema, so without it 0001 fails |
| `CREATE` on `_timescaledb_internal` for `thesada_app_admin` | a continuous aggregate's materialization hypertable lives in that schema and changes owner with it, so the same rule applies there |

The app's migration integration test applies every migration as `thesada_app` on a fresh PostgreSQL 17 TimescaleDB container bootstrapped with exactly these grants. Then run `migrate` once, and it applies 0001 through the latest in one run.

## Configuration

Secrets reach the app through the environment only. With Compose they live in `app.env` and `db.env` (mode `0600`, which is what `startup.sh` chmods them to); the standalone binary reads them from its process environment.

| Variable | Purpose |
|---|---|
| `THESADA_DATABASE_URL` | tenant-scoped, RLS-enforced app role (required) |
| `THESADA_DATABASE_URL_ADMIN` | bypass-RLS, audit-logged role; defaults to the app URL |
| `THESADA_DATABASE_URL_MQTT` | telemetry-ingest role; defaults to the app URL |
| `THESADA_COOKIE_SECRET` | 32+ random bytes signing session cookies (required) |
| `THESADA_MQTT_URL` | broker URL, e.g. `mqtt://broker:1883` |
| `THESADA_MQTT_USER` / `_PASS` | broker credentials, if the broker requires them |
| `THESADA_MQTT_TOPIC_ROOT` | topic prefix; default `thesada` |
| `THESADA_CA_DIR` | device-CA directory; default `/opt/thesada-app/ca`, persist it |
| `THESADA_CA_KEY_PASSPHRASE` | encrypts the on-disk CA key |
| `THESADA_BASE_URL` | public URL for email links; default `http://localhost:8080` |
| `THESADA_ADMIN_EMAIL` | first super-admin; created on first boot if missing, then idempotent (later boots leave an existing user untouched) |
| `THESADA_SMTP_HOST` / `_PORT` / `_USER` / `_PASS` / `_FROM` | outbound mail; empty host logs links instead of sending |
| `THESADA_TELEGRAM_BOT_TOKEN` | optional alert fan-out |
| `THESADA_TRUSTED_PROXIES` | comma-separated IPs/CIDRs of your reverse proxy; required for `X-Forwarded-Proto`/`X-Forwarded-For` to be honoured (Secure cookies, HSTS, real client IPs) |
| `THESADA_ALERT_MAX_ATTEMPTS` | delivery attempts per alert before dead-letter; default `5` |
| `THESADA_ALERT_RETRY_BASE` | first retry delay, doubles per attempt; default `1m` |
| `THESADA_ALERT_REDISPATCH_INTERVAL` | sweep cadence for undelivered alerts; default `1m` |

### Database pools

The app opens up to three role-scoped connection pools and exits if any fails its open-time ping.

| Pool | Source env | Role intent |
|---|---|---|
| App | `THESADA_DATABASE_URL` | RLS-enforced, tenant-scoped reads and writes |
| Admin | `THESADA_DATABASE_URL_ADMIN` | bypass-RLS, audit-logged cross-tenant work |
| MQTT | `THESADA_DATABASE_URL_MQTT` | the telemetry-ingest subscriber |

The Admin and MQTT pools default to the App connection string unless set separately.

### Device CA persistence

The app issues each paired device an mTLS client certificate from a CA it keeps in `THESADA_CA_DIR`. Persist that directory (the Compose stack mounts a named volume) so paired devices keep their trust anchor across restarts. See [Admin: pairing]({{ site.baseurl }}/app/admin.html) for how certificates are issued.

## Startup sequence

With no subcommand the binary brings the server up in this order: config load, signal context, open the DB pools, service-layer init, tenant and settings cache warm, CA bootstrap, mailer and alert and WebSocket setup, admin-user bootstrap, MQTT subscriber, HTTP server, then block on signal. HTTP routing splits three ways: `/api/v1/` is the JSON API behind bearer-or-cookie auth, `/ws` is the WebSocket hub requiring session auth, and everything else is the web frontend.

On SIGINT or SIGTERM the HTTP server gets a 10-second graceful drain before the process exits.

## Hardening checklist

The quickstart is a starting point, not a production deployment.

- [ ] Front the app with a TLS reverse proxy; keep `8080` bound to localhost.
- [ ] Set `THESADA_TRUSTED_PROXIES` to the proxy's address - forwarded headers from unlisted peers are ignored, so without it cookies lose their Secure flag behind the proxy.
- [ ] Replace the plaintext broker with TLS + per-device mTLS and ACLs.
- [ ] Use managed or backed-up storage for the TimescaleDB and CA volumes.
- [ ] Run `ca-encrypt` so the CA key is encrypted at rest.
- [ ] Set a real `THESADA_BASE_URL` and SMTP so login links resolve and send.
