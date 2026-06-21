---
title: App
nav_order: 4
has_children: true
description: "thesada-app - the web application for managing devices: tenants, telemetry, alerts, config management, and the /api/v1 surface."
---

# App

The Thesada web application manages devices, tenants, telemetry, and alerts, and serves the `/api/v1` surface used by client apps. This section documents its architecture, configuration, the admin interface, deployment, and the API.

---

## Quick links

| | |
|---|---|
| [Architecture]({{ site.baseurl }}/app/architecture.html) | System overview, data flow, components, where state lives |
| [Config Management]({{ site.baseurl }}/app/config.html) | Drift detection and version history of device config and scripts |
| [Admin UI]({{ site.baseurl }}/app/admin.html) | Web interface walkthrough and permission scopes |
| [Deployment]({{ site.baseurl }}/app/deploy.html) | Self-host: binary or Docker Compose, migrations, configuration |
| [API (`/api/v1`)]({{ site.baseurl }}/app/api.html) | Auth, endpoints, request/response shapes |
