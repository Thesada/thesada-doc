# Security Policy

## Reporting a Vulnerability

Email **daniel@hit-con.ca** with a description of the issue and steps to reproduce. Please do not open a public issue for security reports.

Response target: acknowledgement within 5 business days.

## Coordinated Disclosure

This project follows a **90-day coordinated disclosure** policy. After reporting:

1. Maintainer confirms receipt and assesses severity.
2. Both parties agree on a fix timeline (typically within 90 days).
3. A fix is released before public disclosure.

## Scope

**In scope:**

- Documentation content in this repository that could mislead users into insecure configurations
- Jekyll build configuration that could introduce supply-chain or XSS risks via the generated site

**Out of scope:**

- Vulnerabilities in Jekyll, Just the Docs, or Cloudflare Pages - report these to their maintainers
- The firmware or infrastructure this documentation describes - see the thesada-fw repository for firmware security reports

## Deployment Context

This repository contains static documentation hosted on Cloudflare Pages. It does not execute any server-side code or handle user authentication. The attack surface is limited to the static site build pipeline and content accuracy.

## Supported Versions

Only the content on the `main` branch is supported.
