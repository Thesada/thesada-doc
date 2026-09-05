---
title: Admin UI
parent: Web App
nav_order: 3
description: "The super-admin web interface: tenants and users, devices and pairing, per-device config, the MQTT shell, waitlist, and impersonation."
---

# Admin UI

The admin interface lives under `/admin` and is **super-admin only** - every route is gated by the super-admin role. Tenant-level admins (the `is_admin` flag on a user) manage their own tenant through the normal dashboard, not through `/admin`.

This page is a tour of each admin area.

## Tenants

`/admin/tenants` lists every tenant and lets you create one (slug plus display name) or delete one. Within a tenant, `/admin/tenants/{slug}/users` manages its users:

| Action | What it does |
|---|---|
| Create user | add a user to the tenant |
| Edit | change display name or email |
| Send reset | email the user a password-reset link |
| Toggle admin | grant or revoke the tenant-admin flag |
| Delete | remove the user (you cannot delete your own account, and super-admins cannot be deleted) |

## Devices

`/admin/devices` lists devices across all tenants. From here you can:

- **Reassign** a device to a different tenant.
- **Delete** a device - a cascade that returns the device to its unpaired state, clears its certificate, and restarts it so it can be re-provisioned cleanly.
- **Bulk** actions across a selection.

### Pairing

`/admin/devices/pair` issues and revokes per-device mTLS certificates. Issuing signs a client certificate from the internal CA, stores it, and pushes it to the device; revoking removes it. `/admin/ca.crt` downloads the CA certificate. The same issuance is available programmatically - see [API: pair]({{ site.baseurl }}/app/api.html).

## Device config

`/admin/devices/{id}/config` is the per-device config and scripts workspace:

- View the current `config.json` and Lua scripts (kept in sync by [Config Management]({{ site.baseurl }}/app/config.html)).
- Run a CLI command against the device and poll for its result.
- Write a file (config or script) back to the device.
- Snapshot the assembled content and browse the version history.

### Device secrets

`/admin/devices/{id}/secrets` holds the per-device overrides for the write-only secret fields (`mqtt.password`, `telegram.bot_token`, `web.password`, `wifi.ap_password`, per-SSID WiFi passwords). Values are encrypted at rest and never displayed; the page shows two columns, **Stored** (the app store) and **Device** (the live NVS state, read over MQTT when the device answers). Setting a field stores it. **Provision to device** pushes every stored value to an already-paired device over MQTT, and **Clear** drops an override so the device falls back to the tenant default at the next provision. The same page exists per tenant at `/admin/tenants/{slug}/secrets` for the defaults. Use this page rather than the CLI box on the config workspace: `secret.set` is a raw `<field>\n<value>` payload with no JSON envelope, which that box cannot send. The whole feature is off until `THESADA_DEVICE_CONFIG_KEK` is set, see [Deployment]({{ site.baseurl }}/app/deploy.html).

## MQTT shell

`/admin/mqtt` is a live broker shell: subscribe to topics and publish messages over a WebSocket, on the same broker connection as the ingest pipeline. Useful for inspecting raw device traffic.

## Waitlist

When invite-only mode is on, signups land on `/admin/waitlist`. Review an entry and either convert it into a user, provisioning the account, or delete it.

## Impersonation

`/admin/impersonate/{slug}` lets a super-admin view the platform as a given tenant for support and debugging; the data views switch to that tenant. Clear it to return to the full cross-tenant view.

## Debug

`/admin/debug` surfaces runtime diagnostics for troubleshooting.
