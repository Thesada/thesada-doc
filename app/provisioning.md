---
title: Provisioning
parent: Web App
nav_order: 6
description: "Bringing a tenant and its devices online: creating a tenant, issuing MQTT credentials, and the device pairing flow."
---

# Provisioning

Provisioning ends with a device that is a fully isolated, certificate-authenticated MQTT client. Creating a tenant is a database row and nothing more; all the MQTT credential and ACL work happens per device.

There are two routes to a provisioned device:

| Route | Who drives it | Certificate reaches the device over |
|---|---|---|
| [Self-service enrollment](#self-service-enrollment) | the device plus the user who owns it | HTTPS, the device fetches it |
| [Operator pairing](#pairing-a-device) | a super-admin, from the admin UI | the MQTT CLI, the app pushes it |

Self-service enrollment is the route for a factory-fresh device: it never touches the broker until it already holds a certificate. Operator pairing is the super-admin route for a device that is already connected on the shared password credential.

This page covers both, plus the revoke and delete paths that tear them down. The admin routes themselves are toured in [Admin UI]({{ site.baseurl }}/app/admin.html); the on-device side of the cert and port swap is under [Firmware Config]({{ site.baseurl }}/firmware/config.html).

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

## Self-service enrollment

A factory-fresh device has no tenant, no owner, and no credential, so it cannot authenticate to anything. Enrollment is how it gets one without an operator touching the broker on its behalf.

The device's half of it rests on the identity it mints on first boot: a `device_id` derived from its factory MAC, and an Ed25519 keypair whose private half never leaves NVS. See [Firmware Provisioning]({{ site.baseurl }}/firmware/provisioning.html#device-identity).

### Enrollment flow

The app half of this flow is live. The device half - the firmware enrollment client and the setup portal that shows the claim QR and claim code - is the next firmware milestone; until it ships, devices are provisioned through the operator pair flow above.

| # | Step | Actor | Endpoint or route |
|---|---|---|---|
| 1 | Announce the device id, public key and a claim token; receive a challenge | device | `POST /api/v1/devices/enroll` |
| 2 | Return an Ed25519 signature over the challenge | device | `POST /api/v1/devices/enroll/verify` |
| 3 | Claim the device into a tenant | a signed-in user | `POST /devices/claim` |
| 4 | Collect the certificate; 204 until step 3 has happened | device | `POST /api/v1/devices/enroll/cert` |
| 5 | Confirm the certificate is stored, which seals the enrollment | device | `POST /api/v1/devices/enroll/ack` |

Nothing touches the broker before step 4 completes. Wire-level request and response shapes are in [API]({{ site.baseurl }}/app/api.html#device-enrollment).

### What each credential is for

The claim token and the signature answer different questions, and the flow needs both:

| Credential | Proves | Failure without it |
|---|---|---|
| Ed25519 signature over the challenge | the caller holds the device's private key | a photographed QR would be enough to claim a device off a shelf |
| Claim token from the device's own setup page | the claimer has physical access to the hardware | any signed-in user could claim any device the moment they guess its id |

The challenge is single-use and expires after five minutes, and it is consumed whether or not the signature verifies, so a failed attempt burns the nonce rather than leaving it grindable.

### Enrollment rows

Unclaimed devices are not `devices` rows. They live in `device_enrollments`, which has no tenant column, because an unclaimed device genuinely belongs to nobody and modelling "nobody" as a holding tenant would mean a user-facing endpoint reading through the privileged pool. Claiming graduates the enrollment into a `devices` row.

| Property | Value |
|---|---|
| Row identity | `(device_id, pubkey_hex)`, not `device_id` alone |
| Claim token | stored as a SHA-256 hash, never plaintext, compared in constant time |
| Challenge | cleared the moment it is answered |
| Unclaimed row lifetime | 24 hours since last seen, then pruned |
| Claimed row lifetime | never pruned by age |

Keying on the pair rather than the id alone is what stops a lockout. Device ids come from sequentially assigned factory MACs, so holding one unit tells you its neighbours' ids - the id is a guess, not a credential. If rows were keyed on the id, the first caller to announce would own it, and a remote caller who guessed one could pin its own keypair, satisfy the proof with it, and lock the real hardware out permanently. With the pair as the key, the squatter and the real device each get their own row, and the squatter's row is inert: claiming needs the token from the device's own setup page, and the public key is not derivable from anything the device broadcasts over the air.

Multiple rows per `device_id` are therefore expected rather than a fault, bounded by the per-device rate limit on the announce endpoint and cleared by the pruning sweep.

### Claiming, from the user's side

`/devices/claim` is a form that takes two values, and any signed-in user can reach it:

| Field | Source |
|---|---|
| Device ID | the device's setup portal (planned - see the note under Enrollment flow), e.g. `thesada-0123456789ab` |
| Claim code | the same portal. It rotates per portal session, so a rejected code means reload the device page and use the new one |

It is **not** a browsable list of unclaimed devices, and that is a security decision rather than a UI preference. Enrollments have no tenant until they are claimed, so any list of them is inherently cross-tenant: showing one would let any signed-in user claim any device on the deployment the moment they know its id, and ids are guessable from a neighbouring unit. The authorization model cannot express the rule that would be wanted either, since an action is either super-admin-only or open to everyone. Requiring the claim token from the device's own setup page makes physical possession the authorization, which is the property that matters and the only one available.

Claims are capped per user per hour (`THESADA_DEVICE_CLAIM_MAX_PER_HOUR`, default 5). An unknown device id and a wrong claim token return the same message, so the form cannot be used to confirm that a device id exists. A device that has not finished proving possession yet is refused with a "try again shortly" message rather than being bound to hardware that may not be the unit on the label.

### What a claim does

| # | Step | Notes |
|---|---|---|
| 1 | Flip the enrollment to claimed and insert the `devices` row | one transaction - both, or neither |
| 2 | Create the dynsec role and client for the device | network call, idempotent, retried independently |

The owner and the MQTT topic prefix are written at step 1 and nowhere else on this path. The prefix has to be written now because it is otherwise only ever set from the MQTT ingest path, and a device that has never published would leave it null - which yields a broker ACL that does not match what the device eventually publishes on.

Step 2 failing is a hard error surfaced to the user, not a warning: without the dynsec client the device's future certificate is inert and it would silently never connect. Retrying the claim is safe - the first step is idempotent on a row already claimed by the same tenant and user, and the broker calls tolerate "already exists".

**The certificate is not issued here.** The device fetches it itself in step 4 of the flow, which is what keeps its private key off this request path entirely.

### Why the device seals the enrollment, not the app

`POST /devices/enroll/cert` hands over a certificate but does not mark the enrollment delivered. The device does that with a separate acknowledgement once the pair is stored and validated on its side.

Sealing at hand-over looks natural and is wrong: the seal would commit before a byte reached the socket, so a dropped TLS session or a proxy timeout mid-write would leave the app believing the device is provisioned while the device has nothing. The certificate endpoint would then refuse forever and the unit is bricked short of an operator re-pair. Letting the device close the loop makes that failure a retry instead - until the acknowledgement arrives the endpoint re-signs, and each issue supersedes the last, so a retry costs a wasted certificate rather than dead hardware.

Once sealed, the row is terminal. A second delivery needs an explicit re-pair, so a leaked claim token cannot be redeemed twice. Revoking a pair and deleting a device both clear the device's enrollment rows, so the next announce starts a fresh cycle.

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

Steps 2 to 4 and step 8 run over the shared password credential, which reaches only the firmware's pairing allow-list: provisioning, restart and read-only board identification, plus `config.set` on `mqtt.port` alone and `cert.clear` only while the stored cert is broken. Nothing that reads the filesystem, dumps config, or runs code is reachable until the device is on its own certificate. The full command table lives in [Firmware Security]({{ site.baseurl }}/firmware/architecture/security-deps.html#mqtt-cli-authorization).

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
| 5 | Clear the device's enrollment rows | best-effort, so the next announce starts a fresh cycle |

Step 5 matters for anything enrolled self-service: a sealed enrollment row left behind would mean the device could never prove itself again, which is a brick short of manual SQL.

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
| 5 | Clear the device's enrollment rows | best-effort, so the hardware can enrol again |
| 6 | Write a tombstone | prevents MQTT ingest re-creating the row |

Step 4's foreign-key cascade drops the device's telemetry, alerts, certificates, and config-snapshot files. The tombstone stops the ingest pipeline from re-creating the device row from a retained broker message after an app restart. The way back is a fresh enrollment or an operator re-pair. Bulk delete runs the identical per-device sequence; a selection that spans more than one tenant is rejected unless the cross-tenant action is explicitly confirmed.

## Reassigning a device

Reassigning a device to another tenant updates only the `tenant_id` column in the database. The on-device `mqtt.topic_prefix` must be updated out of band - the move does not push new config to the device, and it does not re-provision the dynsec role or ACLs. To move a device cleanly between tenants, re-pair it after reassigning so its credentials and topic scope match the new tenant.

## Deleting a tenant

Deleting a tenant runs a single `DELETE FROM tenants`; device rows cascade by foreign key. The `default` tenant cannot be deleted, and a super-admin cannot delete the tenant they are currently impersonating. Delete tenant devices individually (or revoke them) before removing the tenant so their broker-side credentials are cleaned up as part of the per-device teardown.

## Where this is not the credential

API tokens are a separate surface. `/api/v1` is authenticated by 90-day bearer tokens (SHA-256 hashed at rest) that identify human users of the dashboard and client apps - see [API]({{ site.baseurl }}/app/api.html). They have no relationship to the per-device certificates or dynamic-security clients described here.

