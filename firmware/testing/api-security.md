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
| POST `/api/cmd` `{"cmd":"xyzzy"}` | `{"ok":false,"output":["Unknown command: xyzzy  (type 'help')"]}` (firmware from 2026-11-01 on, older releases answer `ok:true`) |
| POST `/api/cmd` with wrong password | `401 Unauthorized` |
| GET `/api/auth/check` while `web.password` is default or empty | `403`, error names the locked admin surface |
| POST `/api/cmd` with malformed JSON body | `400` / `{"ok":false,"error":"..."}` |

**Test script:**
```bash
python tests/test_firmware.py --web-pass "$WEB_PASS"
```

---

## 6. Security

<!-- claim: repo=thesada-fw ref=dev file=lib/thesada-mod-httpserver/src/HttpServer.cpp match="static bool _authOrReply\(" -->
**Rate limiting** - 5 wrong credentials from one source IP lock it out of every authenticated route for 30 s, with `429`. The count is shared, so guesses on `/api/config` or `/api/cmd` count the same as on `/api/login`.

Start with a clean counter for your IP (one valid login, or 10 min without a failure) and use a password that is not `web.password`. Request 7 checks that a valid login is refused during the lockout:

```bash
for i in 1 2 3; do
  curl -s -o /dev/null -w "$i GET /api/config %{http_code}\n" -u admin:wrong http://[ip]/api/config
done
for i in 4 5; do
  curl -s -o /dev/null -w "$i POST /api/cmd %{http_code}\n" -u admin:wrong \
    -H "Content-Type: application/json" -d '{"cmd":"heap"}' http://[ip]/api/cmd
done
curl -s -w " %{http_code}\n" -u admin:wrong http://[ip]/api/auth/check
curl -s -o /dev/null -w "7 valid login %{http_code}\n" -u "admin:$WEB_PASS" http://[ip]/api/auth/check
# 1-5 /api/config and /api/cmd -> 401 (before 2026-11-08 firmware, POST 5 already answers 429)
# 6 /api/auth/check -> {"ok":false,"error":"Too many attempts - wait 30s"} 429
# 7 valid login during the lockout -> 429
```

**WebSocket auth** - a connection without a valid token is refused at the handshake:

```bash
curl -i http://[ip]/ws/serial \
  -H "Upgrade: websocket" \
  -H "Connection: Upgrade" \
  -H "Sec-WebSocket-Key: dGhlc2FtcGxlbm9uY2U=" \
  -H "Sec-WebSocket-Version: 13"
# -> 401, no log lines. The device logs web.ws_rejected reason=no_token
```

**WS token endpoint** - requires auth, returns a single-use token (30 s, bound to your IP):

```bash
curl http://[ip]/api/ws/token
# -> {"ok":false,"error":"Unauthorized"}

curl -u "admin:$WEB_PASS" http://[ip]/api/ws/token
# -> {"ok":true,"token":"<32 hex>"}
# then connect to ws://[ip]/ws/serial?token=<32 hex> within 30 s. A second use answers 401.
# With 4 grants open the endpoint answers 503 until one is used or expires.
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

# ...but not when a browser reports the request as cross-site
curl -s -u "admin:$WEB_PASS" -X POST http://[ip]/api/cmd \
  -H "Sec-Fetch-Site: cross-site" \
  -H "Content-Type: application/json" -d '{"cmd":"version"}'
# -> 401. Device logs web.basic_refused reason=cross_site method=POST
#    url=/api/cmd, throttled to one line per minute.

# A plain cross-site GET is unaffected - it changes nothing
curl -s -u "admin:$WEB_PASS" -H "Sec-Fetch-Site: cross-site" http://[ip]/api/config
# -> {"ok":true,...}

# ...but the two side-effect GETs are refused
curl -s -u "admin:$WEB_PASS" -H "Sec-Fetch-Site: cross-site" http://[ip]/api/ws/token
curl -s -u "admin:$WEB_PASS" -H "Sec-Fetch-Site: cross-site" http://[ip]/api/auth/check
# -> 401 for both, and neither counts toward the login lockout
```

The 5-failure lockout counts only a credential that was actually offered
and wrong. A cross-site refusal never reached the password check, and a
request carrying no credential attempted nothing, so neither is counted -
otherwise a page on another origin could lock an operator out of their own
device with five requests it cannot read.

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
