# Deployment Guide

## Current Scope

The application currently implements internal authentication, TOTP MFA, login protection, role authorization, session revocation, security auditing, upload-validation infrastructure, and verified public booking.

Services, customer management, POS, operational monitoring, reports, forecasting, notifications, live dashboards, and system-health tooling remain placeholders. Do not deploy expecting those modules to process production business transactions.

## Prerequisites

- Python compatible with Django 5.2
- A virtual environment and pip
- PostgreSQL for production, or SQLite for local development
- SMTP credentials for production email
- Persistent database and media backups
- A persistent writable media directory outside static roots
- A production WSGI/ASGI server and reverse proxy, which are not bundled here
- Redis for shared multi-worker MFA and email counters

## Local Setup

Windows PowerShell:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Load the copied development values into the current PowerShell process:

```powershell
Get-Content .env |
  Where-Object { $_ -match '^[^#][^=]*=' } |
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value
  }
```

macOS/Linux:

```bash
python3 -m venv venv
. venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
set -a
. ./.env
set +a
```

The application does not automatically load `.env`. Export its values through the shell, service manager, container platform, or secret manager.

Initialize the database and load demo data:

```text
python manage.py migrate
python manage.py createsuperuser
python manage.py seed_demo_data --customers 50 --appointments 150 --transactions 300
python manage.py check
python manage.py test
python manage.py runserver
```

The seed_demo_data command creates:
- 1 OWNER account (owner@getnailed.local / DemoOwner@123456)
- 1 CASHIER account (cashier@getnailed.local / DemoCashier@123456)
- 8 STAFF accounts with varied permissions (staff0-7@getnailed.local / DemoStaff0-7@123456)
- 50 realistic customers
- 150 appointments with mixed statuses (COMPLETED, PENDING, APPROVED, etc.)
- 300+ POS transactions spanning 6 months (~$75,710 total revenue)

This is for development/demo only. All demo passwords must be changed before production use.

**Expected Test Results**:
- Found 166 test(s)
- System check identified no issues (0 silenced)
- Ran 166 tests in ~65.8 seconds
- OK

Configure `MFA_ENCRYPTION_KEY` before enrolling MFA. A superuser is created as a verified OWNER and is directed to enroll MFA when owner enforcement is enabled.

## Required Production Environment

At minimum:

```text
DJANGO_ENV=production
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<long random stable secret>
DJANGO_ALLOWED_HOSTS=app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
PUBLIC_BASE_URL=https://app.example.com
DJANGO_MEDIA_ROOT=/srv/get-nailed/media
MFA_ENCRYPTION_KEY=<separate long random stable secret>
DJANGO_CACHE_BACKEND=django.core.cache.backends.redis.RedisCache
DJANGO_CACHE_LOCATION=redis://127.0.0.1:6379/1
```

Recommended PostgreSQL values:

```text
DB_ENGINE=django.db.backends.postgresql
DB_NAME=get_nailed
DB_USER=<restricted application user>
DB_PASSWORD=<secret>
DB_HOST=<database host>
DB_PORT=5432
```

Production startup rejects debug mode, weak/example secrets, wildcard hosts, non-HTTPS trusted origins or public URL, missing explicit media root, non-SMTP email, incomplete SMTP settings, and non-Redis cache configuration.

## Email Setup

Configure production SMTP:

```text
DJANGO_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=<SMTP user>
EMAIL_HOST_PASSWORD=<SMTP secret>
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_TIMEOUT=10
DEFAULT_FROM_EMAIL=no-reply@example.com
```

`EMAIL_USE_TLS` and `EMAIL_USE_SSL` cannot both be true. Port 587 normally uses TLS; port 465 normally uses SSL. Confirm provider requirements.

Send a controlled acceptance email:

```text
python manage.py shell -c "from django.core.mail import send_mail; print(send_mail('Get Nailed SMTP test', 'SMTP is working.', None, ['recipient@example.com']))"
```

Also manually verify activation, password-reset, booking verification, booking confirmation, password-change, MFA-change, new-device, and lockout emails. Never use real credentials in test messages.

## Static And Media Files

Run:

```text
python manage.py collectstatic --noinput
```

Serve `STATIC_ROOT` through the reverse proxy or static service. Production media must:

- Use the explicit `DJANGO_MEDIA_ROOT`
- Remain outside `static/` and `staticfiles/`
- Persist across releases
- Be writable only as required by the application account
- Disable script execution and directory listing at the web server
- Receive `nosniff` and appropriate content-type headers
- Be included in backup and restore procedures

Django serves media directly only in development when `DEBUG=True`.

Service images are stored below `service-images/` with generated UUID names. Database and media backups must be coordinated because image storage is not part of the database transaction.

Load the optional realistic Stage 1 catalog into an empty development/demo database with:

```text
python manage.py loaddata stage1_catalog
```

The fixture is not intended to be repeatedly loaded into a populated production catalog.

## Deployment Commands

Run with the intended environment injected:

```text
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py test
python manage.py collectstatic --noinput
```

Create migrations during development with `python manage.py makemigrations`, review them, and commit them before deployment. Deployment and CI must use `--check --dry-run` to detect uncommitted model drift without creating files.

Do not silence failed security checks. Resolve them or document why the target production architecture makes a warning inapplicable.

Schedule stale booking expiry:

```text
python manage.py expire_unverified_bookings
```

Use Task Scheduler, cron, or the hosting platform scheduler.

## HTTPS And Proxy Controls

- Keep `SECURE_SSL_REDIRECT=True` in production.
- Keep secure session and CSRF cookies enabled.
- Set explicit hosts and HTTPS CSRF origins.
- Enable HSTS only after every required hostname is permanently HTTPS-capable.
- Do not use Django `runserver` in production.
- Validate TLS-terminating proxy behavior. `SECURE_PROXY_SSL_HEADER` is not currently configured and may require an architecture-specific code change.
- Ensure upstream logs redact booking, activation, and password-reset tokens; application redaction does not control proxy logs.

## Backup And Rollback

Back up the database and media root together. Store encryption keys and environment configuration separately from data backups.

- Stop writes before copying SQLite.
- Use approved `pg_dump` and `pg_restore` procedures for PostgreSQL.
- Encrypt backups and restrict access.
- Test restoration in an isolated environment.
- Record the application revision and migration state with each backup.

Application rollback does not automatically reverse schema changes. Reverse migrations may lose data. Prefer a tested, version-matched database and media restore when schema rollback is unsafe.

No automated backup, restore, or rollback tooling is implemented by this repository.

## Manual Acceptance Checks

1. HTTPS host, static assets, and security headers load correctly.
2. OWNER password login requires MFA.
3. CASHIER MFA is enforced when internal MFA policy is enabled.
4. OWNER can invite CASHIER and STAFF and activation email arrives.
5. Activation GET changes no state; CSRF-protected POST continues setup.
6. Invalid login attempts trigger CAPTCHA and temporary lockout.
7. Lockout expires and owner clearing requires reauthentication.
8. Restricted users receive HTTP 403 on owner URLs.
9. Password change/reset revokes other sessions.
10. Account deactivation terminates active sessions.
11. Public booking verification, expiry, resend, token isolation, cancellation, and rescheduling work.
12. Audit events appear without passwords, OTPs, or tokens.
13. Database and media survive restart/release.
14. SMTP works after a process restart.
15. Placeholder pages are identified and are not represented as complete modules.
16. OWNER can create/edit services and upload a validated image; CASHIER sees only active catalog entries.
17. Replacing or deleting a service image removes the old stored file after commit.
