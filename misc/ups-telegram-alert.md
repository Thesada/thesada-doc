---
title: UPS On-Battery Telegram Alert
parent: Misc
nav_order: 2
description: "Send Telegram alerts when UPS switches to battery power using NUT and Home Assistant automations."
---

# UPS On-Battery Telegram Alert

Send a Telegram notification when the UPS switches to battery power.
Uses the NUT integration in HA to monitor UPS status on the Proxmox host.

---

## Prerequisites

- NUT configured on the Proxmox host with `upsd` bound to the LAN IP
  (not `0.0.0.0` -- see [NUT UPS troubleshooting](../troubleshooting/nut-ups-ha) for secure setup)
- Host firewall rule restricting port 3493 to the HA IP only
- NUT integration added in HA via the GUI
- Telegram integration configured
  (see [Telegram Integration](../home-assistant/telegram))
- Router firewall rule allowing DMZ -> LAN on port 3493
  (HA in DMZ needs to reach Proxmox upsd on the main LAN)

---

## NUT Entities

After adding the NUT integration in HA, several entities are created.
The key one for this automation is the UPS status sensor.

The entity name depends on your UPS name in `ups.conf` on the Proxmox
host. Common patterns:

| Entity ID | Description |
|---|---|
| `sensor.ups_status` | UPS status string (e.g. "OL" = online, "OB" = on battery) |
| `sensor.ups_battery_charge` | Battery charge percentage |
| `sensor.ups_load` | Current load percentage |
| `sensor.ups_input_voltage` | Input voltage from mains |

Check **Settings** > **Devices & Services** > **NUT** to see the
exact entity IDs for your setup.

---

## Automation: On-Battery Alert

```yaml
automation:
  - alias: "UPS On Battery Alert"
    triggers:
      - trigger: state
        entity_id: sensor.ups_status
        to: "OB"
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: >
            UPS is on battery power.
            Battery: {{ states('sensor.ups_battery_charge') }}%
            Load: {{ states('sensor.ups_load') }}%
```

This fires the moment the UPS status changes to "OB" (on battery).

---

## Automation: Power Restored

```yaml
automation:
  - alias: "UPS Power Restored"
    triggers:
      - trigger: state
        entity_id: sensor.ups_status
        from: "OB"
        to: "OL"
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: >
            UPS back on mains power.
            Battery: {{ states('sensor.ups_battery_charge') }}%
```

Notifies when power returns ("OL" = on line / mains power).

---

## Automation: Low Battery Warning

```yaml
automation:
  - alias: "UPS Low Battery Warning"
    triggers:
      - trigger: numeric_state
        entity_id: sensor.ups_battery_charge
        below: 30
    conditions:
      - condition: state
        entity_id: sensor.ups_status
        state: "OB"
    actions:
      - action: notify.send_message
        data:
          entity_id: notify.telegram_notify
          message: >
            UPS battery below 30%.
            Battery: {{ states('sensor.ups_battery_charge') }}%
            Load: {{ states('sensor.ups_load') }}%
            Consider shutting down non-essential services.
```

Only fires when on battery AND charge drops below 30%. The condition
prevents false alarms during normal charging cycles.

---

## NUT Status Codes

Common `ups.status` values:

| Code | Meaning |
|---|---|
| OL | On line (mains power, normal) |
| OB | On battery |
| LB | Low battery |
| OB LB | On battery and low battery |
| FSD | Forced shutdown |
| CHRG | Charging |
| TRIM | Trimming voltage (high input) |
| BOOST | Boosting voltage (low input) |

Some UPS models combine codes (e.g. "OB LB" for on battery with low
charge). If your UPS does this, the state trigger `to: "OB"` will not
match "OB LB". Use a template trigger instead:

```yaml
triggers:
  - trigger: template
    value_template: >
      {{ 'OB' in states('sensor.ups_status') }}
```

This matches any status containing "OB", including "OB LB".

---

## Notes

- The NUT integration polls the UPS at a regular interval (default
  varies). There may be a short delay between the actual power loss
  and the alert arriving.
- If HA itself loses power (UPS runs out), no alert will fire. For
  critical infrastructure, consider a separate low-power monitoring
  device that alerts independently.
- Test the automation by pulling the UPS power cable briefly (if safe
  to do so) or by using the Developer Tools > States to manually set
  the sensor value to "OB".
