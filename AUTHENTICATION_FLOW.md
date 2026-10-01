# Authentication Flow

## Internal Account Lifecycle

1. An OWNER opens Internal Accounts and submits a server-validated invitation for CASHIER or STAFF.
2. The new account is inactive, email-unverified, marked as an inactive staff member, and has no usable password.
3. The server generates a random activation token, stores only its digest, and sends the link by email.
4. GET displays an activation confirmation page without changing account or session state.
5. A CSRF-protected POST verifies the token, rotates the anonymous session ID, and stores the activation UUID in the session.
6. The user sets a password that passes Django validation.
7. The server marks the email verified and activates the account.
8. The activation record is marked used and cannot be reused.

Activation links expire according to `ACCOUNT_ACTIVATION_TIMEOUT`. Invalid POST attempts are capped by `ACCOUNT_ACTIVATION_MAX_ATTEMPTS`.

## Password Login

1. The login form limits and validates the email and password on the server.
2. The identifier is normalized to lowercase email.
3. django-axes evaluates failures for the normalized email and remote IP.
4. CAPTCHA is required after `LOGIN_CAPTCHA_THRESHOLD` recent failures.
5. The authentication backend verifies the password and account eligibility.
6. Ineligible and invalid credentials return the same public message.
7. Five failures by default trigger a temporary email-and-IP lockout.
8. If the account has TOTP, login pauses at the MFA challenge.
9. A valid TOTP or unused recovery code completes authentication.
10. The session ID rotates, login failures reset, and role routing selects the dashboard.

## MFA Requirements

- OWNER MFA is controlled by `MFA_ENFORCE_OWNER` and defaults to required.
- CASHIER and STAFF MFA can be required by `MFA_REQUIRE_INTERNAL_USERS` or the OWNER-managed MFA policy.
- Enrolled TOTP is challenged during login even when enrollment is optional.
- Required users without TOTP are restricted to enrollment, reauthentication, and logout routes.
- Invalid MFA codes are limited per account by `MFA_FAILURE_LIMIT` for `MFA_FAILURE_TIMEOUT_MINUTES`.

## Password Reset

1. The server validates and normalizes the email before lookup or rate-limit key creation.
2. The response remains generic whether the account exists or is eligible.
3. Only active, verified, unlocked, password-enabled accounts receive reset email.
4. Email and IP throttles limit reset delivery.
5. Django signs a time-limited reset token.
6. The reset form enforces password policy and rejects the current password.
7. Successful reset invalidates all active database sessions.
8. The reset token becomes unusable after the password change.

The expiry is configured through `PASSWORD_RESET_TIMEOUT`.

## Authenticated Password Change

1. The user supplies the current password.
2. The new password must match confirmation, pass validators, and differ from the current password.
3. The server saves the password and records a security event.
4. All sessions are revoked.
5. The initiating request is logged out.
6. A security notification is sent without including the password.

## Sensitive Reauthentication

Recent reauthentication defaults to five minutes through `SENSITIVE_ACTION_REAUTHENTICATION_MINUTES`. It protects:

- OWNER MFA policy changes
- Login-lockout review and clearing
- Recovery-code regeneration
- TOTP deactivation
- Logout of all devices

The protected action remains server-authorized after reauthentication. Reauthentication does not replace role or object authorization.

## Session Termination

Sessions are invalidated after:

- Password change or reset
- Account deactivation or staff deactivation
- Lock-state, role, superuser, staff, or capability changes
- MFA removal or recovery-code reset
- Explicit logout-all action
- Role-specific inactivity timeout

Current-device logout requires POST. Logout-all requires authentication and recent reauthentication.

## Generic Failure Messages

The application avoids confirming whether an account or booking exists. Operators must not change public messages to expose eligibility, lock state, verification state, or record existence.
