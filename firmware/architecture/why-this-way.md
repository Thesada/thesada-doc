---
title: Why this way
parent: Architecture
grand_parent: Firmware
nav_order: 2
description: "The design decisions behind thesada-fw, stated as opinions: modules and a registry, an event bus, two config layers, a shell over MQTT, Lua in the field, pull OTA, and where it parts ways with ESPHome, Tasmota and plain Arduino."
---

# Why this way

Every choice below could have gone the other way, and several popular projects went the other way. This page says what was chosen and why, in plain words, so you can decide whether the opinions fit your product before you build on them. Nothing here is a criticism of the alternatives; they optimise for a different reader.

| Decision | Instead of | Because |
|---|---|---|
| Modules plus a registry | one `main.cpp` | a new product is a new directory, not a fork |
| Event bus | modules calling each other | a module that knows no other module can be dropped without a rebuild of anything else |
| Compile-time enables and runtime config, both | one or the other | flash is decided at build time, behaviour in the field |
| A shell over MQTT | a REST API on the device | the same command works over serial, HTTP and a 20 kbit cellular link, and the device needs no inbound port |
| Lua on the board | alert logic in C++ | the rule changes at 3 am, the firmware does not |
| Pull OTA with a manifest | push from a server | the device decides when it has the link and the heap for it |

## Modules and a registry

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ModuleRegistry.h match="define MODULE_REGISTER\(CLASS, PRIO\)" -->
A module is a class with `begin()`, `loop()` and `name()`, registered by one macro at the bottom of its own file. `main.cpp` includes no module and calls `ModuleRegistry::beginAll()` and `loopAll()`. Boot order comes from a priority on the registration, so the power manager is up before the modem, the modem before anything that publishes, the services that expose Lua bindings before the Lua engine creates its state, and the engine before the sensors whose events its rules read.

The alternative, one `main.cpp` that knows every sensor, is faster to write for the first board and slower for every board after it. This firmware grew out of one product and now builds three board families from one tree, and the difference between them is which directories are compiled in. That is the whole argument.

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/ModuleRegistry.cpp match="\[\"enabled\"\] \| m->coreModule\(\)" -->
The registry also owns the activation gate: a module runs only when its `config.json` block says `"enabled": true`, unless it declares itself core. Default off is a deliberate cost. A forgotten flag means a silent sensor, but the reverse, a module you did not ask for initialising hardware you do not have, was worse.

## An event bus, not direct calls

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/EventBus.h match="static void subscribe\(const std::string& event, EventCallback cb\)" -->
Modules publish JSON on a named event and subscribe to names. The temperature module does not know that the SD logger, the web dashboard, the MQTT client and the Lua engine all read its output; it would be identical if none of them existed. That is the property that lets a product leave a module out of the build without touching the ones it keeps.

The cost is real: there is no compile-time check that anyone listens, and the payload shape is a convention, not a type. The pages under [Architecture]({{ site.baseurl }}/firmware/architecture/overview.html) and [MQTT Topics]({{ site.baseurl }}/firmware/mqtt-topics.html) are where those conventions are written down, and the spec-drift gate on this site checks the ones that matter against the source.

## Two config layers

<!-- claim: repo=thesada-fw file=src/thesada_config.h match="#define ENABLE_TEMPERATURE" -->
`src/thesada_config.h` decides what is in the binary: `#define ENABLE_TEMPERATURE` and friends, with per-board overrides underneath. `config.json` on the filesystem decides what runs and how: pins, intervals, thresholds, the `enabled` flag per module. The split looks like duplication until you have a fleet. Flash size and the set of drivers are a build decision that ships with a release; a pin or an interval is a field decision that ships with `config.set` over MQTT and survives the next OTA.

<!-- claim: repo=thesada-fw file=README.md match="313 KB" -->
The minimal core-only build is about 313 KB smaller than the full one, which is the number that lets a rescue image squeeze through a weak link.

## A shell over MQTT

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/cli_topics.h match="CLI_TOPIC_RESPONSE" -->
Every shell command has one implementation, and it answers on serial, the WebSocket terminal, `POST /api/cmd` and MQTT alike. Over MQTT the topic is the command, the payload is the argument, and the answer comes back on `<prefix>/cli_response`, deliberately outside the `cli/#` wildcard the device subscribes to so it never hears its own replies.

A REST API on the device would have meant an inbound port, a listener that has to be reachable through whatever NAT the site has, and a second implementation of every command. The broker connection already exists, is outbound, and works over the cellular modem's AT stack where a socket library would not. The trade is that a shell has no schema: responses are lines of text in a JSON envelope, and a client that wants structure parses it. The [CLI Reference]({{ site.baseurl }}/firmware/cli-reference.html) is the contract.

## Lua for the logic that changes

<!-- claim: repo=thesada-fw file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="lua_setglobal\(gL, \"io\"\)" -->
Alert thresholds, sustain counters, cooldowns and MQTT bridges live in `/scripts/rules.lua`, not in C++. `lua.reload` over MQTT tears the state down and re-runs the scripts; the firmware binary is untouched. The runtime is sandboxed: `io`, `os`, `debug` and `package` are nil, so a broker credential is not a root shell on the board, and the native bindings (`Config`, `MQTT`, `EventBus`, `Node`, `JSON`, `Log`, plus `Telegram` when that module is built) cover what a rule legitimately needs.

<!-- claim: repo=thesada-fw file=lib/thesada-mod-scriptengine/src/ScriptEngine.cpp match="MAX_TIMERS = 8" -->
<!-- claim: repo=thesada-fw file=src/thesada_config.h match="LUA_GC_INTERVAL_MS" -->
The limits are those of a microcontroller: eight concurrent timers, a state the [Lua Scripting]({{ site.baseurl }}/firmware/lua-scripting.html) page sizes at about 30 KB, and a garbage collector run on a fixed cadence because a low-allocation workload starves the incremental one. If your rule needs more than that, it is a module.

## Pull OTA, checked before it is applied

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="sha256" -->
The device fetches a JSON manifest from a URL it holds in config, compares the version, streams the binary into the spare partition, verifies the SHA256 against the manifest, and aborts before activation when it does not match.

<!-- claim: repo=thesada-fw file=lib/thesada-core/src/OTAUpdate.cpp match="OTA_CA_PROGMEM" -->
The CA for that TLS session is a file on the filesystem, with a bundle baked into the firmware underneath it for the case where someone flashed without the data partition. A push model would need the device reachable and awake at the moment the server chose; a device on a solar budget and a cellular fallback chooses its own moment.

Two limits, stated in the [README](https://github.com/Thesada/thesada-fw#known-limitations-and-ugly-corners) as well: the SHA256 proves the download arrived intact, not who built it, since there is no signing; and the rollback partition is enabled but the application does not mark itself valid after a boot, so the first self-reboot after an update rests on what the Arduino core does, which is unverified.

## Where it departs from the neighbours

These are the projects most readers arrive from. The differences are about who the reader is, not about quality.

| | ESPHome | Tasmota | Plain Arduino sketch | thesada-fw |
|---|---|---|---|---|
| Configuration | YAML, compiled per change | web UI and console at runtime | code | compile-time enables plus a JSON file, both versioned |
| Where logic lives | YAML lambdas, compiled | rules language in the console | code | Lua on the filesystem, hot reloaded |
| Adding a sensor nobody wrote | a component in the ESPHome tree | a driver in the Tasmota tree | in the sketch | a directory in this repo, one macro |
| Remote control | Home Assistant API | MQTT commands and web UI | whatever you wrote | one shell, four transports |
| Off-grid and cellular | not the target | not the target | yours to build | the original use case |

ESPHome is the right answer when Home Assistant is the whole world and a rebuild per change is fine. Tasmota is the right answer for a commodity plug that should just work. A sketch is right for one board on a bench. This firmware is for the case in between: a product of your own, several boards, poor links, and logic that has to change without a laptop present.

If that is you, [Getting started]({{ site.baseurl }}/getting-started.html) gets a board publishing in half an hour, and [Build your first module]({{ site.baseurl }}/tutorials/first-module.html) is the first thing to do after.
