---
title: Provisioning
parent: Web App
nav_order: 6
description: "Bringing a tenant and its devices online: creating a tenant, issuing MQTT credentials, and the device pairing flow."
---

# Provisioning

Provisioning takes a device from a fresh, password-authenticated connection to a fully isolated, certificate-authenticated MQTT client. There are two distinct steps with very different scopes: creating a tenant (a database row and nothing more) and pairing a device (where all the MQTT credential and ACL work happens). This page covers both, plus the revoke and delete paths that tear them down. The admin routes themselves are toured in [Admin UI]({{ site.baseurl }}/app/admin.html); the on-device side of the cert and port swap is under [Firmware Config]({{ site.baseurl }}/firmware/config.html).

## Creating a tenant

Creating a tenant inserts one row into the `tenants` table (slug as primary key, display name, an auto-generated UUID) and updates the in-memory slug cache so the MQTT ingest hot path picks the tenant up immediately - no restart. **That is the entire operation.** No dynamic-security, MQTT, or certificate work happens at tenant-create time. Isolation is not a tenant-level construct; it is enforced per device, at pair time, through topic-scoped ACLs.

The slug must match `^[a-z0-9-]{3,32}$` and must not be on the reserved list, enforced both in the app and as a database CHECK:

| Reserved slugs (blocked) |
|---|
| `admin`, `system`, `api`, `provision`, `status`, `info`, `sensor`, `alert`, `cli`, `cmd`, `homeassistant` |

### Topic prefix convention

Every device publishes under a topic prefix. The canonical prefix is stored in the device's `mqtt_topic_prefix` column, written when the device publishes its retained `/info` (the prefix is taken from the topic that message arrived on). Until the device has published an `/info` message, the app falls back to a constructed prefix:

| | Value |
|---|---|
| Stored prefix | `mqtt_topic_prefix` column (set on the device's retained `/info`) |
| Fallback formula | `<root>/<tenant-slug>/<device-id>` |
| Root default | `thesada` (env `THESADA_MQTT_TOPIC_ROOT`) |
| Typical per-device prefix | `thesada/<tenant>/<device-id>` |

## Pairing a device

Pairing is **super-admin only** and runs from `/admin/devices/pair`. The page lists every device cross-tenant, unpaired rows sorted first, each with a status badge and an action:

| Row state | Actions shown |
|---|---|
| Unpaired | Issue + push, Delete |
| Paired | Revoke, Delete |

Issuing a pair (`POST /admin/devices/{id}/pair/issue`) creates exactly one dynamic-security role and one client - **per device, not per tenant** - signs a certificate, and pushes everything to the device over MQTT.

### Credentials created at pair time

| Artifact | Value |
|---|---|
| Certificate CN | `thesada-<tenant>-<device-id>` |
| Dynsec client username | the TLS CN (identical to above) |
| Dynsec client password | empty - auth is cert-only |
| Dynsec role | `device-<tenant>-<device-id>` |
| Cert validity | 365 days |

The mTLS listener uses `use_identity_as_username`, so the certificate CN becomes the dynamic-security username directly. There is no password on the listener path; the certificate is the credential. Re-issuing a certificate is a one-click action - there is no automated rotation.

### ACLs baked into the role

The role's ACLs are set once, at pair time, from the device's tenant and the `mqtt_cross_tenant_read` setting:

| Direction | Topic | Scope |
|---|---|---|
| Publish | `<prefix>/#` | always - the device's own prefix |
| Publish | `homeassistant/#` | always |
| Subscribe + receive | `homeassistant/#` | always |
| Subscribe + receive | `thesada/#` | when cross-tenant read is on |
| Subscribe + receive | `thesada/<tenant>/#` | when cross-tenant read is off |

The write path (publish) is always narrow: a device can only publish under its own prefix and to Home Assistant discovery. The read path is governed by `mqtt_cross_tenant_read`, which defaults to **on for the `default` tenant** and **off for every other tenant**. The broad-read default lets dashboards in a single-tenant homelab receive sensor data from the whole `thesada/#` tree; scoped tenants only see their own subtree. Home Assistant topics sit outside the tenant tree and are always readable.

`mqtt_cross_tenant_read` is operator-flippable at runtime, but the value is **read once and baked into the role at pair time**. Changing the setting on an already-paired device has no effect until you re-pair it; there is no mechanism to push updated ACLs to a live role.

### Pair flow, step by step

`POST /admin/devices/{id}/pair/issue` runs push-first, persist-last so the database row only reflects what the device actually has:

| # | Step | Transport |
|---|---|---|
| 1 | Sign cert from the internal CA (`CN=thesada-<tenant>-<device-id>`, 365d) | local CA |
| 2 | Push `client_cert` PEM via `cert.set` (10s) | MQTT CLI |
| 3 | Push `client_key` PEM via `cert.set` (10s) | MQTT CLI |
| 4 | Push `config.set mqtt.port 8884` | MQTT CLI |
| 5 | Create dynsec role with the ACLs above (10s) | dynsec |
| 6 | Create dynsec client (CN as username, empty password, role attached) (10s) | dynsec |
| 7 | Persist the cert row and flip `paired_at` | Postgres |
| 8 | Publish `<prefix>/cli/restart` `{}` (fire-and-forget) | MQTT |

The `cert.set` payload is `<part-type>\n<PEM>` - the part type, a newline, then the full PEM.

A successful issue emits a `device.pair.state_change` audit log (`unpaired` -> `paired`, reason `pair_issue`) with the device, tenant, and operator email.

### Why a restart, not a config reload

The device boots into mTLS on the next restart rather than reloading config in place. The firmware's `config.set` already refreshes its in-memory config, so a follow-up `config.reload` would see the old port equal to the new port and skip the reconnect entirely. A restart is atomic: the device boots, reads `config.json` (port 8884) and the NVS cert, and engages mTLS on its first connection.

The restart publish is best-effort - a failure is logged as a warning, not an error, and does not roll back the cert or the database row, both of which are already written. The port flip was stored to NVS in step 4, so even if the restart message is missed, the device will be on 8884 after its next reboot.

### Ports

| Port | Listener | When |
|---|---|---|
| 8883 | password | pre-pair (plain MQTT, password auth) |
| 8884 | mTLS | post-pair (certificate auth) |

The reverse proxy routes to the matching Mosquitto listener by port; the broker hostname does not change.

### Idempotent retries

`already exists` / `already has` errors from the broker on the role-create and client-create steps are swallowed. A mid-flow retry - for example an MQTT timeout after the dynsec steps succeeded but before the database persist - will not fail on the dynsec work.

## First connection after pairing

On the post-restart boot the firmware reads `config.json` (port 8884) and the NVS cert, then connects to the mTLS listener with the pushed client cert and key. The broker maps the TLS CN to the dynsec username (`thesada-<tenant>-<device-id>`); that client carries the pre-provisioned role, which supplies the ACLs. No password is exchanged.

## Revoking a pair

`POST /admin/devices/{id}/pair/revoke` returns a device to password auth and removes its credentials:

| # | Step | Notes |
|---|---|---|
| 1 | Revoke the certificate in the database | load-bearing |
| 2 | `config.set mqtt.port 8883`, `cert.clear`, `restart` on the device | best-effort |
| 3 | Delete the dynsec client | best-effort, 10s |
| 4 | Delete the dynsec role | best-effort, 10s |

The database revoke is the step that matters; the broker rejects the device on its next auth check regardless of whether the dynsec teardown reached the broker. Revoke emits a `device.pair.state_change` audit log (`paired` -> `revoked`, reason `admin_revoke`).

The on-device cleanup runs through a shared three-step sequence: publish `mqtt.port 8883`, then `cert.clear`, then `restart`, each separated by a short pause so the firmware's single-slot CLI ring does not drop the next command. Empty command payloads are sent as `{}` rather than zero-length, for SIM7080G modem compatibility.

## Deleting a device

`POST /admin/devices/{id}/delete` is a hard cascade. The form must echo the device ID back (`confirm_device_id`), checked both client-side and on the server; a mismatch aborts with no deletion. The cascade returns the device to its unpaired, password-auth state and then wipes its data:

| # | Step | Notes |
|---|---|---|
| 0 | On-device reset: port -> 8883, `cert.clear`, `restart` | best-effort |
| 1 | Revoke the certificate | load-bearing - aborts on failure |
| 2 | Delete the dynsec client and role | best-effort, 10s |
| 3 | Clear the device's retained broker topics | best-effort, 10s |
| 4 | Delete the device row (FK cascade) | load-bearing, 30s |
| 5 | Write a tombstone | prevents MQTT ingest re-creating the row |

Step 4's foreign-key cascade drops the device's telemetry, alerts, certificates, and config-snapshot files. The tombstone stops the ingest pipeline from re-creating the device row from a retained broker message after an app restart. Re-pairing is the only way back. Bulk delete runs the identical per-device sequence; a selection that spans more than one tenant is rejected unless the cross-tenant action is explicitly confirmed.

## Reassigning a device

Reassigning a device to another tenant updates only the `tenant_id` column in the database. The on-device `mqtt.topic_prefix` must be updated out of band - the move does not push new config to the device, and it does not re-provision the dynsec role or ACLs. To move a device cleanly between tenants, re-pair it after reassigning so its credentials and topic scope match the new tenant.

## Deleting a tenant

Deleting a tenant runs a single `DELETE FROM tenants`; device rows cascade by foreign key. The `default` tenant cannot be deleted, and a super-admin cannot delete the tenant they are currently impersonating. Delete tenant devices individually (or revoke them) before removing the tenant so their broker-side credentials are cleaned up as part of the per-device teardown.

## Where this is not the credential

API tokens are a separate surface. `/api/v1` is authenticated by 90-day bearer tokens (SHA-256 hashed at rest) that identify human users of the dashboard and client apps - see [API]({{ site.baseurl }}/app/api.html). They have no relationship to the per-device certificates or dynamic-security clients described here.

