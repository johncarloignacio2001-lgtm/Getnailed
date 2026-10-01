# Security Architecture

## Scope

This document describes controls implemented in the current Django application. It is not a claim that the application is fully secure, production-ready, compliant, or complete. Services, customer management, POS, monitoring workflows, reports, forecasting, and notifications remain placeholders.

## Trust Boundaries

| Boundary | Data | Implemented controls |
|---|---|---|
| Browser to Django | Credentials, booking PII, codes, tokens, form input | HTTPS production settings, CSRF middleware, Django forms, bounded inputs, output escaping |
| Authenticated user to privileged views | Session cookie, requested object IDs, role claims | Server-side decorators, capability checks, scoped querysets, recent reauthentication |
| Django to database | Users, sessions, bookings, token digests, audit events | Django ORM parameterization, Argon2 hashes, HMAC digests, database sessions |
| Django to cache | MFA failures, email throttles | Expiring counters; production requires the configured Redis backend |
| Django to SMTP | Activation/reset links, booking codes/tokens, alerts | Environment-only production SMTP, generic responses, email throttling |
| Django to media storage | Public service images | Separate media root, signature validation, generated names, restrictive permissions |
| Owner/DB administrator to security records | Audit and account data | Owner-only read UI and read-only admin; DB administrators remain trusted |

## Authentication Controls

- Internal accounts are invited by an OWNER and begin inactive, unverified, and without a usable password.
- Email addresses are normalized and case-insensitively unique.
- Public registration routes are closed.
- Passwords use Argon2 first, with a 12-character minimum and Django validation.
- Login eligibility requires active status, verified email, unlocked status, and active internal-staff status where applicable.
- Login errors do not distinguish an unknown account, wrong password, or ineligible account.
- django-axes applies email-and-IP throttling and temporary lockout.
- CAPTCHA is introduced after repeated failures.
- TOTP is the only enabled MFA method. Trusted-browser bypass is disabled.
- TOTP failures have a separate per-account temporary limit.
- Recovery codes are keyed hashes, single-use, and replaced as a set during regeneration.
- TOTP secrets are encrypted using the environment-provided MFA key.

See `AUTHENTICATION_FLOW.md` and `MFA_RECOVERY_GUIDE.md`.

## Session Controls

- Only database or cached-database session engines are accepted.
- Session identifiers rotate after login and MFA enrollment.
- OWNER inactivity defaults to 30 minutes; CASHIER and STAFF inactivity defaults to 60 minutes.
- Password, account-state, role, capability, lock, and MFA security changes revoke sessions.
- Current-device and all-device logout are separate actions.
- Sensitive owner and MFA actions require recent reauthentication.
- Session cookies are `HttpOnly` and use `SameSite=Lax` by default.
- Production defaults enable secure cookies and HTTPS redirect.

## Authorization Controls

Authorization is enforced in Python views and querysets, not by hidden fields, menu visibility, JavaScript, posted role names, or posted user IDs.

- OWNER bypasses operational capabilities and accesses owner security surfaces.
- CASHIER receives the implemented operational capability set but not owner administration.
- STAFF receives assigned-work access and optional explicit capabilities.
- CUSTOMER is excluded from internal data surfaces.
- Anonymous users are redirected from protected routes and may use public booking flows.
- Public booking access is possession-based: reference plus verified bearer token.

See `ROLE_PERMISSION_MATRIX.md`.

## Booking Controls

- Public booking does not create a user account.
- Verification codes are eight digits, expire, have a failure cap, and are stored only as HMAC digests.
- Resends use generic responses, cooldowns, limits, and invalidate old codes.
- Successful verification issues a random access token stored only as a digest.
- Tokens are bound to one booking and expire.
- Status, cancellation, and rescheduling revalidate the token server-side.
- Verification and token comparisons use constant-time comparison.
- Token-bearing application audit paths are redacted.

## Input And Upload Controls

- State-changing views bind Django forms and consume only `cleaned_data`.
- Phone numbers, references, codes, tokens, emails, passwords, MFA codes, and signed lockout values have server-side limits.
- Browser role choices are restricted and owner authorization is rechecked in the form.
- No application raw SQL is used; database access uses the Django ORM.
- Template autoescaping remains enabled; no first-party `safe`, `mark_safe`, or `autoescape off` use remains.
- All browser POST forms include CSRF tokens and no first-party CSRF exemption exists.
- `Service.image` uses `apps/core/upload_security.py` to validate image size, extension, declared MIME, Pillow-detected format/signature, corruption, decompression warnings, and pixel count.
- Safe image paths use UUID names rather than user filenames.
- Production requires an explicit media root separate from static roots.
- Replaced and deleted service images are removed from storage after the database transaction commits.
- Service image mutations are OWNER-only; catalog reads are limited to OWNER and CASHIER.

## Audit Controls

`SecurityEvent` records semantic actions including login, logout, lockout, activation, password changes, MFA changes, role changes, session revocation, denied access, reauthentication, and booking verification. Records contain request ID, remote address, user agent, safe target, timestamp, and result, but no arbitrary request payload.

`AuditLog` records authenticated state-changing HTTP requests. Audit displays are OWNER-only and admin records cannot be added, changed, or deleted through Django admin.

Audit data resides in the application database. It is not tamper-evident against a database administrator and has no configured retention, export, WORM storage, or alerting pipeline.

## Production Configuration

Required or security-relevant variables are documented in `.env.example` and `DEPLOYMENT.md`. Important secret values include:

- `DJANGO_SECRET_KEY`
- `MFA_ENCRYPTION_KEY`
- `DB_PASSWORD`
- `EMAIL_HOST_PASSWORD`

Never commit real values. Use a secret manager or service environment in production.

## Known Limitations

- POS prices, sales, discounts, payments, receipts, voids, and server-calculated financial totals are not implemented.
- Service catalogs, business hours, staff availability, overlap detection, duration, and scheduling conflict controls are not implemented.
- Booking bearer tokens appear in URLs and may reach browser history, email systems, proxy logs, or infrastructure outside application audit redaction.
- Service upload validation is live and tested, but it does not re-encode images, remove metadata, or scan malware.
- Development local-memory counters are process-local and reset on restart. Production requires Redis, whose availability, persistence, and monitoring remain deployment responsibilities.
- Audit events share the primary database and are not cryptographically chained or exported to immutable storage.
- No Content Security Policy is configured.
- No automated backup, restore, key rotation, or incident alerting system is included.
- No supported administrator-assisted MFA recovery workflow exists.
- Production app-server, reverse-proxy, TLS, and media-serving configurations are deployment-specific and not included.
