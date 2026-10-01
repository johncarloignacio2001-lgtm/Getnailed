# MFA Recovery Guide

## Supported Method

The application supports authenticator-app TOTP only. SMS, email OTP, trusted-browser bypass, and WebAuthn are not enabled.

## Enrollment

1. Sign in with a verified account.
2. Open Account Security or follow the mandatory enrollment redirect.
3. Reauthenticate if prompted.
4. Scan the QR code with an authenticator application.
5. Enter the current six-digit code.
6. Save every displayed recovery code before leaving the page.

TOTP secrets are encrypted before database storage. Recovery codes are shown once and stored only as keyed digests.

## Using A Recovery Code

1. Enter email and password normally.
2. At the MFA prompt, enter one unused recovery code instead of a TOTP code.
3. The code is consumed transactionally and cannot be reused.
4. Review account security after login and regenerate codes if exposure is suspected.

Do not email recovery codes, paste them into support tickets, or store them in the application database as plaintext.

## Regenerating Recovery Codes

1. Sign in and complete MFA.
2. Open Account Security.
3. Choose recovery-code regeneration.
4. Complete recent reauthentication.
5. Confirm that all old codes should be invalidated.
6. Save the new set immediately.

Regeneration deletes all previous recovery-code records, emits an audit event, sends a security notification, and revokes active sessions.

## Lost Authenticator And Lost Codes

The current UI has no administrator-assisted MFA reset flow. If both the authenticator and all recovery codes are unavailable, normal self-service recovery cannot complete.

An organization-approved incident process should:

1. Lock or deactivate the account if compromise is possible.
2. Verify identity out of band using an approved method.
3. Record the approver and evidence without recording secrets.
4. Use only a separately reviewed administrative recovery procedure.
5. Force fresh TOTP enrollment and recovery-code generation.
6. Revoke sessions and review roles and capabilities.

Direct database edits are not a supported routine recovery mechanism.

## MFA Failure Lockout

Invalid TOTP and recovery-code attempts share a per-account counter. The default is five failures followed by a 15-minute temporary block. Configure with:

- `MFA_FAILURE_LIMIT`
- `MFA_FAILURE_TIMEOUT_MINUTES`

The development cache is process-local. Production settings require Redis so multiple workers use a shared counter. Redis availability, access control, persistence, and monitoring must be verified during deployment.

## Encryption-Key Handling

- `MFA_ENCRYPTION_KEY` must be long, random, stable, and separate from `DJANGO_SECRET_KEY`.
- Comma-separated keys allow TOTP decryption rotation, with the current encryption key first.
- Losing all applicable keys makes existing TOTP secrets unreadable.
- Recovery-code digests use the configured MFA key string. Changing it invalidates existing recovery codes.
- No bulk TOTP re-encryption command is implemented.

Plan and test key rotation before changing production values.
