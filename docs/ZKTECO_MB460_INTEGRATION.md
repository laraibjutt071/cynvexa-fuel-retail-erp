# ZKTeco MB460 Biometric Integration — Future Architecture

## Status: NOT IMPLEMENTED — Architecture Document Only

This document describes the planned integration path for the ZKTeco MB460
biometric attendance device. No hardware integration, SDK usage, or live
device communication exists in the current codebase. The attendance module
currently operates in **manual-first** mode only.

---

## Device Overview

- **Model:** ZKTeco MB460 (multi-biometric: face + fingerprint + palm)
- **Connectivity:** Ethernet (TCP/IP), optional Wi-Fi
- **Protocol:** ZKTeco's proprietary PUSH protocol over HTTP, or pull via
  the ZK Web API (ADMS / ZKBioAccess)
- **On-device storage:** Up to 2,000 face templates, 3,000 fingerprints
- **Capacity:** 100,000 transaction records

## Integration Architecture

### Option 1: PUSH Mode (Recommended)

The MB460 can be configured to POST attendance events to an HTTP endpoint
as they occur (real-time push).

```
[MB460 Device] --HTTP POST--> [CYNVEXA Backend: /api/biometric/webhook]
                                      |
                                      v
                            [Parse event, map user]
                                      |
                                      v
                            [Create/update AttendanceRecord]
                                      |
                                      v
                            [Write audit log entry]
```

**Endpoint design:**

```
POST /organizations/{org_id}/stations/{station_id}/biometric/webhook
Content-Type: application/json (or form-encoded, per ZKTeco format)

{
  "device_serial": "MB460-001",
  "event_type": "check_in" | "check_out",
  "employee_id": "EMP001",      // device-side user ID
  "timestamp": "2026-11-15T08:03:22+05:00",
  "verify_mode": "face" | "fingerprint" | "palm",
  "photo_base64": "..."         // optional face photo
}
```

**Security:**

- Webhook authenticated via a per-device shared secret (header or query
  parameter), stored in station configuration.
- IP allowlisting at the reverse proxy (Caddy/nginx) level.
- The webhook endpoint does NOT require JWT authentication (the device
  cannot hold a user session), but does require the shared secret.

**User mapping:**

- Each device stores users by a numeric `employee_id`.
- CYNVEXA maintains a mapping table (`biometric_user_mappings`) that links
  `device_serial + employee_id` → `users.id`.
- Enrollment is done through the MB460's built-in UI (face/fingerprint
  capture), then the mapping is recorded in CYNVEXA by the Station Manager.

### Option 2: PULL Mode (Fallback)

If PUSH is unreliable (network issues), a scheduled background task polls
the device's HTTP API every N minutes.

```
[CYNVEXA Backend: scheduled task]
        |
        v
GET http://<device-ip>:4370/iclock/getrequest
        |
        v
[Parse transaction log, create AttendanceRecords]
```

This requires the device IP to be reachable from the backend server, which
may not be feasible in a hosted/cloud deployment without a VPN or tunnel.

## Database Changes Required (Future Migration)

```sql
CREATE TABLE biometric_devices (
    id UUID PRIMARY KEY,
    station_id UUID REFERENCES stations(id) ON DELETE CASCADE,
    device_serial VARCHAR(100) UNIQUE NOT NULL,
    device_model VARCHAR(50) NOT NULL DEFAULT 'MB460',
    ip_address VARCHAR(45),
    webhook_secret VARCHAR(200) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE biometric_user_mappings (
    id UUID PRIMARY KEY,
    device_id UUID REFERENCES biometric_devices(id) ON DELETE CASCADE,
    device_employee_id VARCHAR(50) NOT NULL,
    user_id UUID REFERENCES users(id) ON DELETE RESTRICT,
    enrolled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(device_id, device_employee_id)
);
```

## Existing Compatibility

The current `AttendanceRecord` model already has a `source` field
(default: `"manual"`). Biometric-sourced records would use
`source = "biometric"` with no schema change needed.

The `check_in_time` and `check_out_time` fields accept `time` values,
which the webhook would extract from the device timestamp.

## Implementation Phases

1. **Phase A (Current):** Manual attendance only. No device integration.
2. **Phase B:** Device registration UI, user-to-device mapping table,
   webhook endpoint, PUSH mode integration.
3. **Phase C:** Real-time attendance dashboard updates (WebSocket or
   polling), photo capture display.
4. **Phase D:** Multi-device support, PULL mode fallback, offline
   reconciliation.

## Hardware Procurement

The ZKTeco MB460 is NOT procured or on-site. This document is for
architectural planning only. Estimated hardware cost: PKR 25,000–35,000
per unit.

## Constraints

- No paid SDKs or cloud services are used.
- The integration uses the device's built-in HTTP push capability, not a
  proprietary Windows-only SDK.
- All attendance data flows through the same `AttendanceRecord` model
  regardless of source (manual or biometric).
