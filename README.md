# Get Nailed Nail Bar and Spa

A Django 5.2 capstone application currently implementing secure internal authentication, TOTP MFA, role-based authorization, security auditing, upload-validation infrastructure, and verified public booking.

## Implementation Status

Implemented:

- OWNER-issued CASHIER and STAFF account invitations
- Verified email/password authentication with Argon2
- OWNER, CASHIER, STAFF, and CUSTOMER authorization
- Fine-grained STAFF capabilities
- TOTP MFA, single-use recovery codes, and MFA attempt limiting
- Login throttling, CAPTCHA, temporary lockout, and session revocation
- Public booking creation, email verification, private access, rescheduling, and cancellation
- Service categories and services with OWNER CRUD, CASHIER catalog access, search, filters, pagination, pricing, and validated images
- OWNER-managed STAFF operational profiles with specialty and availability status
- Owner-visible structured security events and HTTP audit rows
- Server-side input validation, CSRF protection, output escaping, and upload-validation helpers

Placeholder or incomplete:

- Live dashboards
- Customer management
- POS, payments, discounts, receipts, voids, and financial totals
- Service monitoring and assignment workflows
- Reports and exports
- Random Forest forecasting
- Operational notifications
- System health, backup automation, and demo seeding

The presence of a route or permission does not mean its planned business workflow is complete.

## Roles

| Role | Summary |
|---|---|
| OWNER | Security administration and all implemented internal capabilities |
| CASHIER | Operational capabilities without owner administration |
| STAFF | Assigned work plus explicitly granted capabilities |
| CUSTOMER | Optional account role; public registration is not implemented |
| Public | Verified booking access without an account |

See `ROLE_PERMISSION_MATRIX.md`.

## Quick Start

Windows:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py test
python manage.py runserver
```

macOS/Linux:

```bash
python3 -m venv venv
. venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py check
python manage.py test
python manage.py runserver
```

Configure `MFA_ENCRYPTION_KEY` before MFA enrollment. `.env.example` documents available variables, but `.env` is not automatically loaded. Export variables into the process or use the hosting platform environment/secret manager.

## Required Verification

```text
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py test
```

Run `check --deploy` with production-profile environment values. Do not silence failed checks merely to obtain passing output.

## Documentation

- `SECURITY_ARCHITECTURE.md`
- `AUTHENTICATION_FLOW.md`
- `MFA_RECOVERY_GUIDE.md`
- `ROLE_PERMISSION_MATRIX.md`
- `SECURITY_TEST_CHECKLIST.md`
- `INCIDENT_RESPONSE_GUIDE.md`
- `DEPLOYMENT.md`
- `USER_MANUAL.md`
- `DEFENSE_DEMONSTRATION_SCRIPT.md`

## Security Statement

Implemented controls and automated tests reduce known risks in the covered features. They do not prove that the project is secure. Review `SECURITY_ARCHITECTURE.md` for trust boundaries and known limitations before deployment.
