# Incident Response Guide

## Principles

- Protect people and data before preserving convenience.
- Preserve evidence before clearing records or rotating broadly.
- Never place passwords, TOTP secrets, recovery codes, activation tokens, reset tokens, session IDs, cookies, or booking access tokens in tickets or chat.
- Record times in a consistent timezone and include request IDs where available.
- Use approved out-of-band identity verification for account recovery.

## Initial Triage

1. Record reporter, start time, affected users, booking references, systems, and observed behavior.
2. Preserve `SecurityEvent`, `AuditLog`, django-axes records, SMTP-provider records, database logs, and reverse-proxy logs.
3. Correlate application records with `request_id` and the `X-Request-ID` response header.
4. Determine whether the issue affects confidentiality, integrity, availability, or account access.
5. Lock or deactivate affected accounts when continued access is unsafe.
6. Confirm session-revocation events after containment changes.
7. Escalate according to organizational notification and privacy obligations.

## Event Guide

| Event | Meaning | Response consideration |
|---|---|---|
| `LOGIN_FAILED` | Invalid or ineligible login | Review repeated user/IP pattern |
| `ACCOUNT_LOCKED` | Temporary login lockout | Validate activity before clearing |
| `LOGIN_SUCCEEDED` | Completed login | Compare time and device context |
| `UNAUTHORIZED_ACCESS` | Protected route denied | Investigate repetition or privilege probing |
| `PASSWORD_RESET_REQUESTED` | Generic reset request | Confirm user intent if repeated |
| `PASSWORD_CHANGED` | Password changed/reset | Escalate if user denies it |
| `MFA_ENABLED` / `MFA_DISABLED` | MFA state changed | Unexpected disablement is high priority |
| `MFA_RECOVERY_USED` | Recovery code consumed | Confirm intent and consider regeneration |
| `MFA_RECOVERY_RESET` | Recovery set replaced | Confirm authorization and identity |
| `ROLE_CHANGED` | Privileges changed | Validate approval and resulting access |
| `ACCOUNT_DEACTIVATED` | Authentication blocked | Use for containment |
| `SESSION_REVOKED` | Database sessions deleted | Confirm expected trigger |
| `SENSITIVE_REAUTHENTICATION` | Recent authentication completed | Correlate with sensitive action |
| `BOOKING_VERIFIED` | Verification success/failure | Review abuse volume and affected record |

## Suspected Account Compromise

1. Lock or deactivate the account.
2. Preserve login, MFA, role, password, reauthentication, and session events.
3. Review active role and capability assignments.
4. Verify the user out of band.
5. Reset the password and MFA under an approved procedure.
6. Regenerate recovery codes.
7. Revoke all sessions.
8. Restore only approved permissions before reactivation.

## MFA Secret Or Recovery-Code Exposure

1. Contain the account if active exploitation is possible.
2. Revoke sessions.
3. Replace TOTP enrollment and regenerate all recovery codes.
4. Treat downloaded recovery-code files as sensitive local artifacts.
5. If `MFA_ENCRYPTION_KEY` is exposed, assess every enrolled account and follow a tested key-rotation plan.

## Django Secret-Key Exposure

1. Replace `DJANGO_SECRET_KEY` through the deployment secret mechanism.
2. Expect sessions and Django-signed values to become invalid.
3. Reissue activation and reset links as needed.
4. Assess booking digests and application signing behavior.
5. Handle `MFA_ENCRYPTION_KEY` separately.

## Booking Access-Token Exposure

1. Treat the URL as access to booking PII and mutation actions.
2. Preserve it only in restricted evidence storage.
3. Notify the affected customer under organizational policy.
4. Current code has no token-rotation or immediate-revocation UI; document this limitation during response.

## Database Compromise

Assume exposure of user and booking PII, password hashes, sessions, token digests, audit records, and encrypted MFA material.

1. Isolate database access and preserve evidence.
2. Rotate database credentials.
3. Assess `DJANGO_SECRET_KEY` and `MFA_ENCRYPTION_KEY` exposure.
4. Force password/MFA recovery based on the assessed scope.
5. Treat audit records as potentially altered because they share the database.
6. Restore only from a verified backup and validate schema/application compatibility.

## Recovery And Review

1. Verify account states, permissions, sessions, MFA, email delivery, and booking access.
2. Run migrations and security checks in the restored environment.
3. Run the complete automated test suite.
4. Document timeline, root cause, containment, affected records, recovery, and evidence gaps.
5. Add or improve tests for the exact incident path.
6. Record follow-up owners and deadlines.

## Current Operational Limitations

- No SIEM, alerting pipeline, immutable audit destination, or retention automation is configured.
- No automated backup or restore tooling is included.
- No administrator-assisted MFA recovery UI exists.
- No booking token-revocation UI exists.
- Application email is synchronous.
- Infrastructure logs and provider records are outside this repository.
