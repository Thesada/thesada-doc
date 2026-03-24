---
title: mDNS Across VLANs (OpenWrt)
parent: Troubleshooting
nav_order: 1
description: "Fix mDNS discovery across VLANs on OpenWrt using mdns-repeater and correct firewall rules."
---

# mDNS Not Working Across VLANs on OpenWrt

## Symptom

Nodes on the IoT VLAN (172.16.0.0/24) are not discoverable by
.local hostname from the main LAN (10.0.0.0/24). OTA uploads
fail with "can't resolve hostname." Pinging by IP works.

## Cause

mDNS (multicast DNS, UDP port 5353) uses multicast address 224.0.0.251.
Multicast traffic does not cross VLAN boundaries by default. A repeater
is needed to bridge mDNS between subnets.

The common mistake: adding a firewall rule with a destination zone set
(e.g. IOT -> lan). This creates a **forward** rule. mDNS queries from
the LAN need to reach the **router itself** (the input chain), because
`mdns-repeater` listens on the router's interfaces and re-broadcasts
to the other VLAN.

## Fix

### 1. Install mdns-repeater

```
opkg update
opkg install mdns-repeater
```

### 2. Configure mdns-repeater

Edit `/etc/config/mdns-repeater` (or via LuCI: Services > mDNS Repeater):

List all interfaces that should share mDNS: the LAN bridge, the IoT
WiFi AP, and the DMZ VLAN.

```
config mdns_repeater 'main'
	list interface 'br-lan'
	list interface 'phy0-ap0'
	list interface 'br-lan.666@br-lan'
```

- `br-lan` - main LAN bridge
- `phy0-ap0` - dedicated IoT WiFi AP (2.4 GHz)
- `br-lan.666@br-lan` - DMZ VLAN (for ESPHome OTA from HA dashboard)

### 3. Add the firewall rule - no destination zone

This is the critical part. The rule must allow UDP 5353 to 224.0.0.251
with **no destination zone**. Leaving the destination zone empty makes
the rule apply to the **input** chain (traffic destined for the router
itself), not the **forward** chain (traffic passing through the router).

In LuCI: Network > Firewall > Traffic Rules > Add:

| Field | Value |
|---|---|
| Name | Allow-mDNS-IOT |
| Protocol | UDP |
| Source zone | IOT |
| Source address | (leave empty) |
| Destination zone | **leave empty - do not set** |
| Destination address | 224.0.0.251 |
| Destination port | 5353 |
| Action | Accept |

**The destination zone must be empty.** Setting it to "lan" or "Device"
changes the chain the rule applies to and mDNS will not work.

### 4. Restart and test

```
/etc/init.d/mdns-repeater restart
```

From the main LAN:

```
ping your-node.local
```

If it resolves, mDNS is working across the VLAN boundary.

## Why this matters

This allows OTA updates (both ESPHome and custom firmware) to work by
.local hostname across VLANs. Without it, you need static IPs for every
IoT node, which defeats the purpose of mDNS and makes adding new nodes
harder.
