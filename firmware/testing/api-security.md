---
title: API & Security
parent: Testing
grand_parent: Firmware
nav_order: 2
description: "HTTP Shell API, rate limiting, WebSocket auth, config editor, and Lua scripting test procedures."
---

# API & Security

## 5. /api/cmd (HTTP Shell)

All Shell commands are available over HTTP. Requires auth.

**Precondition: a real `web.password`.** The shipped default (`changeme`, an absent key, or an explicit `""`) locks the whole authenticated surface rather than opening it, so every example below fails with the default in place. Set one first, then export it for the examples. On the serial console:

```text
secret.set web.password <your password>
```

Over MQTT the same command takes a raw `<field>\n<value>` payload on `<prefix>/cli/secret.set`, no JSON envelope:

```bash
printf 'web.password\n%s' '<your password>' | mosquitto_pub -t "$prefix/cli/secret.set" -s
```

```bash
export WEB_PASS='<your password>'
```

<!-- claim: repo=thesada-fw file=lib/thesada-mod-httpserver/src/HttpServer.cpp match="admin locked" -->
While the password is still default, `/api/auth/check` answers `403` with `web.password is default/empty - admin locked` so the login modal can say why; every other admin endpoint answers a plain `401`. The firmware logs `web.admin_refused reason=default_password`, throttled to one line a minute.

Run the test script with `--web-pass` to enable automated checks, or test manually with curl:

```bash
# version command
curl -s -u "admin:$WEB_PASS" \
  -X POST http://[ip]/api/cmd \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"version"}'
# -> {"ok":true,"output":["thesada-fw v1.x ..."]}

# default web.password -> 403 on the check endpoint, 401 everywhere else
curl -s -u admin:changeme http://[ip]/api/auth/check
# -> {"ok":false,"error":"web.password is default/empty - admin locked. ..."}

# wrong password -> 401
curl -s -u admin:wrong \
  -X POST http://[ip]/api/cmd \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"version"}'
# -> {"ok":false,"error":"Unauthorized"}
```

| Check | Expected |
|---|---|
| POST `/api/cmd` `{"cmd":"version"}` with correct password | `{"ok":true,"output":["thesada-fw v1.x ..."]}` |
| POST `/api/cmd` `{"cmd":"heap"}` | `{"ok":true,"output":["Free: XXXXXX B ..."]}` |
| POST `/api/cmd` `{"cmd":"xyzzy"}` | `{"ok":true,"output":["Unknown command: xyzzy"]}` |
| POST `/api/cmd` with wrong password | `401 Unauthorized` |
| GET `/api/auth/check` while `web.password` is default or empty | `403`, error names the locked admin surface |
| POST `/api/cmd` with malformed JSON body | `400` / `{"ok":false,"error":"..."}` |

**Test script:**
```bash
python tests/test_firmware.py --web-pass "$WEB_PASS"
```

---

## 6. Security

**Rate limiting** - 5 failed logins lock out the source IP for 30 s:

```bash
for i in $(seq 1 6); do
  curl -s -u admin:wrong http://[ip]/api/auth/check
  echo
done
# Attempts 1-5 -> {"ok":false,"error":"Unauthorized"}
# Attempt 6   -> {"ok":false,"error":"Too many attempts - wait 30s"}
```

**WebSocket auth** - unauthenticated direct connections are rejected:

```bash
curl -i http://[ip]/ws/serial \
  -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlc2FtcGxlbm9uY2U=" \
  -H "Sec-WebSocket-Version: 13"
# -> 101 (handshake completes), then immediately receives WS close frame
# Serial log shows: [WRN][WebServer] WS: rejected - not pre-authorized
```

**WS token endpoint** - requires auth:

```bash
curl http://[ip]/api/ws/token
# -> {"ok":false,"error":"Unauthorized"}

curl -u "admin:$WEB_PASS" http://[ip]/api/ws/token
# -> {"ok":true}
```

**Bearer token auth:**

```bash
# Login - exchange Basic Auth for Bearer token
curl -s -u "admin:$WEB_PASS" -X POST http://[ip]/api/login
# -> {"ok":true,"token":"<32-hex>","expires_in":3600}

# Use token for admin endpoints
TOKEN="<token from above>"
curl -s -H "Authorization: Bearer $TOKEN" -X POST http://[ip]/api/cmd \
  -H "Content-Type: application/json" -d '{"cmd":"version"}'
# -> {"ok":true,"output":["thesada-fw v1.x..."]}

# Invalid token
curl -s -H "Authorization: Bearer invalidtoken" -X POST http://[ip]/api/cmd \
  -H "Content-Type: application/json" -d '{"cmd":"version"}'
# -> {"ok":false,"error":"Unauthorized"}

# Wrong credentials
curl -s -u admin:wrong -X POST http://[ip]/api/login
# -> {"ok":false,"error":"Unauthorized"}

# Rate limiting (after 5 failures)
# -> {"ok":false,"error":"Too many attempts - wait 30s"}

# Basic Auth still works (backwards compatible)
curl -s -u "admin:$WEB_PASS" -X POST http://[ip]/api/cmd \
  -H "Content-Type: application/json" -d '{"cmd":"version"}'
# -> {"ok":true,...}
```

---

## 7. Config Editor

| Check | Expected |
|---|---|
| Admin - Config tab | `config.json` loads in editor |
| Edit `device.friendly_name`, save | Device restarts; new name in footer |
| POST `/api/config` with wrong password | 401, file unchanged |

**Curl test (should return 401):**
```bash
curl -X POST http://[ip]/api/config \
  -u admin:wrongpassword \
  -H 'Content-Type: application/json' \
  -d '{"device":{"name":"hacked"}}'
```

---

## 8. Lua Scripting

| Check | Expected |
|---|---|
| `lua.exec return 42` | `42` |
| `lua.exec Log.info("test")` | `OK` (plus `[INF][Lua] test` in log) |
| `lua.exec bad syntax!!!` | `Error: ...` |
| `lua.reload` | `Lua scripts reloaded` + scripts re-execute |
| Modify `/scripts/rules.lua`, run `lua.reload` | New rule behavior active immediately |
| MQTT message to `<prefix>/cmd/lua/reload` | Same as `lua.reload` |
