# Changelog

## Unreleased

- Added a key capture helper (`tools/key_capture`) that pulls each plug's device name, access key, access token and product key out of the Cloud Intelligence app's traffic and prints them, so you don't have to search mitmproxy by hand.

## 0.1.0 — 2026-11-15

First release.

- Local on/off control and real power state for Cloud Intelligence (Alibaba IoT Living) plugs over ALCS / CoAP.
- UI setup with optional auto-discovery of the plug's IP address.
- Automatic rediscovery when a plug's IP address changes.
- Re-authentication flow for when a plug's keys change.
- Adjustable polling interval (3 to 300 seconds).
