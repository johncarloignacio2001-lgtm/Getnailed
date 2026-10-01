# User Manual

## Getting Started with Demo Data

**Quick Start (Development/Demo)**:

To seed the system with realistic demo data for testing and demonstrations, run:

```bash
python manage.py seed_demo_data --customers 50 --appointments 150 --transactions 300
```

This creates:
- 1 OWNER account (owner@getnailed.local / DemoOwner@123456)
- 1 CASHIER account (cashier@getnailed.local / DemoCashier@123456)
- 8 STAFF accounts with varied permissions (staff0-7@getnailed.local / DemoStaff0-7@123456)
- 50 customers
- 150 appointments with mixed statuses
- 300 POS transactions spanning 6 months (~$75,710 revenue)

**WARNING**: These credentials are **demo-only**. Change passwords immediately before production use or external sharing.

## Current Roles

| Role | Current use |
|---|---|
| OWNER | Security administration, internal invitations, audit, full implemented operational access |
| CASHIER | Operational booking, POS, customer, assignment, monitoring, and daily-summary routes; several are placeholders |
| STAFF | Assigned work and optional capabilities granted by OWNER |
| CUSTOMER | Customer dashboard and public booking functions; public registration is not implemented |
| Public visitor | Create and manage a verified booking with private credentials |

See `ROLE_PERMISSION_MATRIX.md` for exact route access.

## Activating An Internal Account

1. Open the activation link from the invitation email.
2. Review the confirmation page.
3. Select Continue securely.
4. Create a password of at least 12 characters that passes the displayed policy.
5. Sign in using the invited email address.
6. Enroll MFA if required.

Activation links expire and work once. Contact an OWNER if the link is unavailable.

## Signing In

1. Enter the complete email address and password.
2. Complete CAPTCHA if repeated failures triggered it.
3. Enter the authenticator code when prompted.
4. If the authenticator is unavailable, enter one unused recovery code.

Repeated password or MFA failures cause temporary blocking. Public errors do not reveal whether an account exists or why it is ineligible.

## Account Security

Account Security provides TOTP enrollment and recovery-code status. Recovery codes are shown only when created. Store them offline.

Available actions include:

- Change password
- Regenerate recovery codes after reauthentication
- Disable TOTP after reauthentication only when policy does not require it
- Log out the current device
- Log out all devices after reauthentication

Password, role, account, or MFA security changes can terminate active sessions.

## OWNER Tasks

### Invite An Internal User

1. Open Internal Accounts.
2. Enter the employee name, verified destination email, optional phone, and CASHIER or STAFF role.
3. Submit the invitation.
4. Confirm delivery through the configured email provider.
5. Have the employee complete activation and MFA enrollment.

The invitation form cannot create another OWNER. Fine-grained STAFF capability editing is not available in the normal application UI.

### Configure Internal MFA

Open MFA Requirements, reauthenticate, and select whether CASHIER and STAFF must enroll MFA. OWNER enforcement is also controlled by deployment configuration.

### Review Login Lockouts

Open Login Lockouts and reauthenticate. Only current lockouts tied to known accounts are shown. Clear a lockout only after validating that the activity is legitimate. Lockouts also expire automatically.

### Review Audit Activity

Open Audit Trail to review recent security events and authenticated state-changing requests. The screen is read-only. Search, export, retention controls, and external alerting are not implemented.

### Manage Service Categories And Services

1. Open Services to search and filter the current catalog.
2. Open Categories to create or edit salon groupings.
3. Add a service with category, description, duration from 5 to 480 minutes, positive price, active status, and optional image.
4. Upload only JPEG, PNG, or WebP images within the configured byte and pixel limits.
5. Mark historical offerings inactive when they should remain visible to OWNER but unavailable to CASHIER.
6. Reauthenticate before deleting a category or service.

A category that still contains services cannot be deleted. Moving or deleting those services is required first.

### Manage Staff Profiles

1. Open Staff Profiles from the owner navigation.
2. Select an existing STAFF account that does not already have a profile.
3. Record specialty, current appointment availability, and profile active status.
4. Update the operational profile without changing the linked account role or authentication state.
5. Reauthenticate before deleting a profile.

Deleting a StaffProfile does not delete the user account. OWNER, CASHIER, CUSTOMER, and non-STAFF accounts cannot be linked to a StaffProfile.

## Public Booking

1. Open Book an appointment.
2. Enter contact details, requested service text, and a future date/time.
3. Retrieve the eight-digit code from email.
4. Enter the booking reference and code.
5. Save the private confirmation link.
6. Use the link to view, reschedule, or cancel.

Do not share the private link. Anyone who possesses a valid link can access the booking until its token expires.

The current booking form does not validate a service catalog, prices, business hours, staff schedules, duration, availability, or appointment overlap.

## Internal Booking Views

- OWNER and booking managers can view all booking rows.
- STAFF can view assigned bookings only.
- CASHIER can open booking management but not the assigned-appointments route.

Approval, rejection, assignment, detailed status progression, and conflict management are not implemented.

## Current Placeholder Modules

The following routes may be visible according to role but do not yet implement complete business workflows:

- Live dashboards
- Customer record management
- POS sales, discounts, payments, receipts, and voids
- Monitoring and assignment workflow
- Financial reports and exports
- Random Forest forecasting
- Notification center
- System health and backup UI

Do not use placeholder pages as evidence of completed business transactions.

## Reporting A Security Concern

Report unexpected login, password, MFA, recovery-code, role, or booking activity immediately. Do not send passwords, MFA secrets, codes, or private booking links in the report. See `INCIDENT_RESPONSE_GUIDE.md` for operator procedures.
