# Defense Readiness Roadmap

Use `DEFENSE_DEMONSTRATION_SCRIPT.md` for the current executable demonstration and `SECURITY_TEST_CHECKLIST.md` for automated evidence.

## Demonstrable Current Controls

1. Verified internal account activation and password policy.
2. OWNER and CASHIER password-plus-MFA login.
3. Restricted STAFF dashboard and direct URL denial.
4. Login throttling, CAPTCHA, temporary lockout, and expiration.
5. Password/account/MFA session revocation.
6. Public booking verification, token isolation, cancellation, and rescheduling.
7. CSRF, server-side input validation, output escaping, and upload-validator tests.
8. Owner-only structured audit evidence without credentials or tokens.
9. Production-profile Django deployment checks.
10. OWNER service/category CRUD, secure image validation, CASHIER read access, and STAFF profile management.

## Evidence To Prepare

- Complete output from the five required management commands.
- Sanitized production environment variable names, never values.
- SMTP delivery evidence using test accounts.
- Role permission and direct URL test evidence.
- Database and media backup/restore evidence from the target infrastructure.
- Manual acceptance results from `DEPLOYMENT.md`.
- Known limitations from `SECURITY_ARCHITECTURE.md`.

## Future Evidence Not Yet Available

Do not demonstrate or claim these until their modules and tests exist:

- Booking integration with service duration and scheduling-conflict controls
- POS totals, discounts, payment, receipt, rollback, and void controls
- Monitoring assignment and service-status transitions
- Dashboard/report reconciliation
- Forecast data provenance, eligibility, metrics, and insufficient-data behavior
- Automated system health, backup, restore, and immutable audit export
