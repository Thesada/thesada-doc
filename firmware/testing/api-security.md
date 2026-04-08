---
title: API & Security
parent: Testing
grand_parent: Firmware
nav_order: 2
description: "HTTP Shell API, rate limiting, WebSocket auth, config editor, and Lua scripting test procedures."
---

# API & Security

## 5. /api/cmd (HTTP Shell)

All Shell commands are available over HTTP. Requires auth. Run the test script with `--web-pass` to enable automated checks, or test manually with curl:

```bash
# version command
curl -s -u admin:changeme \
  -X POST http://[ip]/api/cmd \
  -H 'Content-Type: application/json' \
  -d '{"cmd":"version"}'
# -> {"ok":true,"output":["thesada-fw v1.x ..."]}

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
| POST `/api/cmd` with malformed JSON body | `400` / `{"ok":false,"error":"..."}` |

**Test script:**
```bash
python tests/test_firmware.py --web-pass changeme
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

curl -u admin:changeme http://[ip]/api/ws/token
# -> {"ok":true}
```

**Bearer token auth (v1.2.4+):**

```bash
# Login - exchange Basic Auth for Bearer token
curl -s -u admin:changeme -X POST http://[ip]/api/login
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
curl -s -u admin:changeme -X POST http://[ip]/api/cmd \
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
