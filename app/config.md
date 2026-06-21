---
title: Config Management
parent: App
nav_order: 2
description: "How the platform tracks, versions, and detects drift in each device's config.json and Lua scripts."
---

# Config Management

The platform keeps a current copy and a full change history of each device's config and Lua scripts, and detects drift automatically - no polling, no scheduled jobs. The on-device `config.json` format itself is documented under [Firmware Config]({{ site.baseurl }}/firmware/config.html); this page covers how the platform tracks and versions those files.

## Drift detection

Detection is hash-based and reactive:

1. Every device publishes a retained `<prefix>/info` message on connect, and re-publishes it after any state-changing command (for example `config.reload`). The payload carries SHA-256 hashes of the on-disk file bytes:
   - `config_hash` - `/config.json`
   - `scripts_main_hash` - `/scripts/main.lua`
   - `scripts_rules_hash` - `/scripts/rules.lua`
2. On each `/info`, the app compares every hash against the latest stored hash for that file.
3. If a hash matches, nothing happens - the stored copy is already current.
4. If a hash differs (or the platform has no copy of that file yet), the app pulls the file over MQTT, validates it, and stores it.

Because the firmware re-publishes `/info` right after a `config.reload`, a change made on the device surfaces in the platform within about a second.

## Pulling a changed file

- **config.json** is pulled with a single `config.dump` command.
- **Lua scripts** are pulled with chunked `fs.cat` (paged reads), since a script can exceed the MQTT buffer. See [Chunked File I/O]({{ site.baseurl }}/firmware/chunked-io.html).

Pulled content is validated before it is stored: a config must parse as a JSON object, and a script must be non-empty and free of shell-error markers. Invalid pulls are discarded rather than recorded.

## What is stored

| Store | Holds |
|---|---|
| current state | one row per (device, path): the file content, its SHA-256, and where the change came from |
| history | an immutable, append-only log; every SHA change is appended with a link to the previous SHA |

A new history row is written only when the content actually changes - a re-reported identical hash does not create one. The result is a forensic chain of every config and script version a device has run, with no duplicate rows.

## Where to see it

The per-device config page in the admin interface shows the current config and scripts, their version history, and lets an operator push a change back to the device. See [Admin UI]({{ site.baseurl }}/app/admin.html).
