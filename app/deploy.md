---
title: Deployment
parent: App
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

## Configuration

Secrets reach the app through the environment only. With Compose they live in `app.env` and `db.env` (mode `0640`); the standalone binary reads them from its process environment.

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
| `THESADA_ADMIN_EMAIL` | first super-admin, bootstrapped on every boot |
| `THESADA_SMTP_HOST` / `_PORT` / `_USER` / `_PASS` / `_FROM` | outbound mail; empty host logs links instead of sending |
| `THESADA_TELEGRAM_BOT_TOKEN` | optional alert fan-out |

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
- [ ] Replace the plaintext broker with TLS + per-device mTLS and ACLs.
- [ ] Use managed or backed-up storage for the TimescaleDB and CA volumes.
- [ ] Run `ca-encrypt` so the CA key is encrypted at rest.
- [ ] Set a real `THESADA_BASE_URL` and SMTP so login links resolve and send.
