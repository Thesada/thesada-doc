---
title: Examples
nav_order: 5
has_children: true
description: "The starter modules in the firmware tree, walked through line by line: what each demonstrates, the config it needs, what it publishes."
---

# Examples

The firmware tree carries a few modules that exist to be read rather than deployed. Each is one header and one source file, under `lib/thesada-mod-example-*/`, off in every build until you turn it on. These pages walk through them. If you want to write one from scratch instead, start with [Build your first module]({{ site.baseurl }}/tutorials/first-module.html).

The modules are on the firmware `dev` branch and ship with the next release; until then, build from `dev` to try them.

| Example | Shape | Demonstrates |
|---|---|---|
| [temperature-mqtt]({{ site.baseurl }}/examples/temperature-mqtt.html) | sensor | a timed read, one publish to MQTT, one to the event bus |
| [remote-relay]({{ site.baseurl }}/examples/remote-relay.html) | actuator | one shell command reachable over serial, HTTP and MQTT, state published on every change |

A third, `blink-led`, is being contributed and gets its page when it lands.

Turning one on takes two switches, the same as for any module: its `ENABLE_EXAMPLE_*` line in `src/thesada_config.h`, and `"enabled": true` in its `config.json` block.
