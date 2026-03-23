---
title: NUT UPS Integration with Home Assistant
parent: Troubleshooting
nav_order: 2
description: "Fix NUT UPS integration not connecting from Home Assistant -- upsd binding, firewall, and secure setup."
---

# NUT UPS Not Connecting from Home Assistant

## Symptom

Home Assistant NUT integration fails to connect to the UPS on the
Proxmox host. Error in HA logs indicates connection refused on port 3493.
The UPS is visible locally on the Proxmox host via `upsc` but HA cannot
reach it over the network.

## Cause

`upsd` (the NUT network server) defaults to listening on localhost only
(127.0.0.1:3493). It does not accept connections from other hosts on
the network unless explicitly configured to bind to all interfaces.

## Debugging

If you are not sure whether the problem is NUT config, firewall, or
network routing, isolate each layer:

### 1. Temporarily open everything

On the Proxmox host, bind upsd to all interfaces:

```
# /etc/nut/upsd.conf
LISTEN 0.0.0.0 3493
```

```bash
systemctl restart nut-server
```

Temporarily disable the Proxmox firewall (or any iptables rules on port 3493).

### 2. Test connectivity from another machine

From any Linux host on the network:

```bash
nc -zv <proxmox-ip> 3493
```

If this succeeds, NUT is listening and the network path is clear. If it
fails, the problem is network/firewall, not NUT config.

Then test the NUT protocol:

```bash
upsc <ups-name>@<proxmox-ip>
```

### 3. Test from the HA host specifically

If `nc -zv` works from your laptop but HA still cannot connect, the
problem is a firewall rule between the DMZ and LAN. Check the router
firewall for a rule allowing DMZ -> LAN on port 3493.

---

## Fix

Once you have confirmed connectivity works with everything open, lock
it down properly.

### 1. Bind upsd to the specific LAN IP

Do not leave upsd on `0.0.0.0` in production. Bind it to the LAN
interface only:

```
# /etc/nut/upsd.conf
LISTEN 10.0.0.10 3493
```

Replace `10.0.0.10` with your Proxmox host LAN IP.

```bash
systemctl restart nut-server
```

### 2. Add a host firewall rule

Restrict port 3493 to the HA IP only. On the Proxmox host:

```bash
# via iptables
iptables -A INPUT -p tcp --dport 3493 -s 192.168.2.20 -j ACCEPT
iptables -A INPUT -p tcp --dport 3493 -j DROP
```

Or add the equivalent via Proxmox Datacenter > Firewall if you use
the built-in firewall. Replace `192.168.2.20` with your HA IP.

This way upsd only listens on the LAN interface AND only accepts
connections from HA. Belt and suspenders.

### 3. Verify

```bash
# from HA subnet - should work
nc -zv 10.0.0.10 3493

# from any other host - should be refused
nc -zv 10.0.0.10 3493
```

### 4. Configure in Home Assistant

Add the NUT integration via the GUI (Settings > Devices & Services > Add Integration > NUT).

| Field | Value |
|---|---|
| Host | Proxmox host LAN IP (e.g. 10.0.0.10) |
| Port | 3493 |
| Username | (as configured in upsd.users) |
| Password | (as configured in upsd.users) |

**Use the GUI, not YAML.** YAML configuration for NUT is deprecated in
current HA versions.

## Notes

- `upsd.users` on the Proxmox host must have a user configured with
  at least `upsmon secondary` permissions for HA to read the data.
- If you change the Proxmox host IP, update both the LISTEN directive
  and the firewall rule.
