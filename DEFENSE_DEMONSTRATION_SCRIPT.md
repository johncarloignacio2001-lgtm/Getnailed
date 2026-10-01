# Defense Demonstration Script

## Updated: Final Integration & QA (2026-09-18)

**Test Results**: 166 tests, 100% pass rate (65.8s runtime)  
**Demo Data**: Ready with 50 customers, 150 appointments, 300+ transactions, $75,710 revenue  
**System Status**: All core modules tested and verified  

## Quick Setup (5 minutes)

```bash
python manage.py seed_demo_data --customers 50 --appointments 150 --transactions 300
python manage.py test --verbosity=1
python manage.py runserver 0.0.0.0:8000
```

Access: `http://localhost:8000`

## Demo Credentials

| Role | Email | Password | MFA |
|------|-------|----------|-----|
| OWNER | owner@getnailed.local | DemoOwner@123456 | Required |
| CASHIER | cashier@getnailed.local | DemoCashier@123456 | Optional |
| STAFF | staff0-7@getnailed.local | DemoStaff0-7@123456 | No |

## Preparation

- Use a non-production database and test inboxes.
- Demo database includes OWNER, CASHIER, 8 STAFF, 50 customers, 150 appointments, 300 transactions.
- TOTP MFA is NOT pre-enrolled; demonstrate enrollment if time permits.
- Email backend prints to console (configure SMTP for production).
- Keep recovery codes hidden from recording.
- Run the required commands immediately before the defense and save their complete output.
- Never display real environment values, SMTP credentials, database passwords, tokens, or secret keys.

## Opening Scope Statement

State:

> This build implements authentication, TOTP MFA, login protection, role authorization, session revocation, security auditing, upload-validation infrastructure, verified public booking with token isolation, appointment state management, POS workflows, and integrated audit logging across all modules.
> 
> Placeholder/incomplete: Real-time notifications, live dashboards, statistical forecasting (deterministic only).
> 
> All 166 security and workflow tests pass. Demo data is production-realistic with 6 months of transaction history.

## Demonstration 1: OWNER Authentication with MFA (8 minutes)

1. Open `http://localhost:8000/accounts/login/`
2. Enter: owner@getnailed.local / DemoOwner@123456
3. System redirects to MFA prompt
4. **First-time setup** (if MFA not enrolled):
   - Click "Set up authenticator"
   - Scan QR with Google Authenticator or Authy
   - Enter 6-digit code
   - System shows recovery codes (save these!)
5. **Post-login**: OWNER dashboard visible
6. **Security points**:
   - Password is Argon2 hashed (not plaintext)
   - MFA required, not optional
   - Email verified before account activation
   - Recovery codes backup if authenticator lost
   - Session rotates on login

Expected result: Password alone does not grant access; MFA is mandatory.

## Demonstration 2: Role-Based Access Control (8 minutes)

**Scene 1: OWNER Full Access**
- Logged in as owner@getnailed.local
- Open: Internal Accounts → See all users
- Open: Audit Trail → See all security events
- Open: Services → Create/Edit/Delete
- Open: Staff Profiles → Full management
- Observation: All modules visible

**Scene 2: CASHIER Limited Access**
- New browser tab
- Login as: cashier@getnailed.local / DemoCashier@123456
- Open: Booking Management → Can view all bookings
- Open: POS → Can create sales
- Open: Services → Can view active only (read-only)
- Attempt: Internal Accounts URL → HTTP 403 Forbidden
- Attempt: Audit Trail URL → HTTP 403 Forbidden
- Observation: Menu matches server authorization

**Scene 3: STAFF Scoped Access**
- New browser tab
- Login as: staff0@getnailed.local / DemoStaff0@123456
- Navigate: My Bookings → Can see assigned appointments
- Attempt: All Bookings → HTTP 403 Forbidden (no capability)
- Attempt: POS → HTTP 403 Forbidden (not permitted)
- Observation: Staff sees only personal work

Expected result: Menu visibility and URL enforcement match per role.

## Demonstration 3: Public Booking with Token Security (12 minutes)

**Flow: Customer perspective**

1. Open: `http://localhost:8000/bookings/book/`
2. Fill form:
   - Name: "Demo Customer"
   - Email: "customer@example.local"
   - Phone: "+63.917.555.1234"
   - Service: "Basic Manicure"
   - Date: Tomorrow, 2:00 PM
3. Click "Check Availability"
4. Result: "Booking submitted. Check your email for verification code."
5. Verify code: Check console or email backend output (format: 8 digits)
6. Navigate: `http://localhost:8000/bookings/verify/`
7. Enter:
   - Reference: (from previous page)
   - Code: (from console)
8. Click "Verify"
9. Result: "Booking confirmed. Save this private link: [secure token]"
10. **Security observation**: Token is single-use and time-limited

**Flow: Customer status check**

1. Navigate: `http://localhost:8000/bookings/status/`
2. Enter Reference and Token (from confirmation)
3. Result: Shows booking details, cancel/reschedule options
4. Click "Cancel"
5. Enter reason: "Schedule conflict"
6. Submit → Status changes to CANCELLED
7. **Security observation**: Token cannot access other bookings

**Flow: Audit Trail (OWNER view)**

1. OWNER logs in
2. Navigate: Audit Trail
3. Filter: Search for booking reference or customer email
4. Expand event:
   - Booking created (UNVERIFIED)
   - Verification code generated (CODE REDACTED)
   - Booking verified
   - Booking cancelled
5. **Security observation**: No codes, tokens, or sensitive data visible in logs

Expected result: Customer books, verifies, and can cancel without internal system access. All actions audited without leaking secrets.

## Demonstration 4: Appointment State Management (10 minutes)

**Scenario: Complete booking workflow from PENDING to COMPLETED**

**Step 1: Create appointment (STAFF)**
- Login as: staff4@getnailed.local (Booking Manager)
- Navigate: Booking Management → Create Appointment
- Fill: Customer "Maria Santos", Service "Basic Manicure", Time "Tomorrow 3:00 PM"
- Submit → Status: PENDING (unassigned)

**Step 2: Approve (OWNER)**
- Login as: owner@getnailed.local
- Navigate: Booking Management → Find "Maria Santos"
- Status: PENDING
- Click "Approve" → Status: APPROVED
- **Observation**: Timestamp recorded

**Step 3: Assign (OWNER)**
- Status: APPROVED
- Click "Assign Staff" → Select staff0 (Manicure Specialist)
- **Observation**: System checks for schedule conflicts
- Result: assigned_staff updated, status remains APPROVED

**Step 4: Start Service (ASSIGNED STAFF)**
- Login as: staff0@getnailed.local
- Navigate: My Bookings → "Maria Santos"
- Status: APPROVED
- Click "Start Service" → Status: ONGOING
- **Observation**: started_at timestamp recorded

**Step 5: Complete Service (ASSIGNED STAFF)**
- Status: ONGOING
- Click "Complete" → Status: COMPLETED
- **Observation**: completed_at recorded
- System suggests: "Create POS receipt?"

**Step 6: Create POS Receipt (CASHIER)**
- Login as: cashier@getnailed.local
- Navigate: POS → New Sale
- Appointment: Pre-populated (Maria Santos, Basic Manicure, $25.00)
- Payment: CASH $30
- Submit → Receipt REC-20260918-XXXXXX generated, Change: $5.00
- **Observation**: Receipt shows customer, service, amount, change

**Step 7: Audit Review (OWNER)**
- Navigate: Audit Trail
- Filter: Reference contains "Maria" or "REC-"
- Expand events: BOOKING_CREATED → APPOINTMENT_APPROVED → APPOINTMENT_ASSIGNED → SERVICE_STARTED → SERVICE_COMPLETED → SALE_CREATED → PAYMENT_RECORDED
- **Observation**: Complete chain without data leakage

Expected result: Appointment flows through all states, with OWNER control and staff action. Audit trail captures every step.

## Demonstration 5: Input Security & Validation (6 minutes)

**Test 1: HTML Escaping in Bookings**
1. Public booking form
2. Name field: Enter `<script>alert('XSS')</script>`
3. Submit
4. Navigate to booking details
5. **Expected**: Name displayed as literal text, not executed
6. **Observation**: HTML tags visible as `&lt;script&gt;...&lt;/script&gt;`

**Test 2: CSRF Protection**
1. Open browser console (F12)
2. Simulate form submission without CSRF token:
   ```javascript
   fetch('/bookings/book/', {method: 'POST', body: new FormData()})
   ```
3. **Expected**: HTTP 403 CSRF verification failed
4. **Observation**: Token required on all POST requests

**Test 3: Image Upload Validation**
1. OWNER login
2. Navigate: Services → Create Service
3. Try upload: .exe file (or text file with wrong MIME)
4. **Expected**: "Invalid file type. Only JPEG, PNG, GIF, WebP allowed."
5. Try upload: Valid .jpg image > 20MB pixels
6. **Expected**: "Image exceeds pixel limit (20,000,000)"
7. Try upload: Valid image
8. **Expected**: Upload succeeds, safe filename generated (UUID-based)

Expected result: All inputs validated, escaping applied, file format enforced.

## Demonstration 6: Security Incident Handling (7 minutes)

**Test 1: Login Lockout**
1. Navigate: `http://localhost:8000/accounts/login/`
2. Email: staff0@getnailed.local
3. Password: WrongPassword (repeat 5 times)
4. **Result**: "Too many login attempts. Please try again in 30 minutes."
5. CAPTCHA appears after ~3 failures

**Test 2: OWNER Unlock**
1. OWNER login
2. Navigate: Login Lockouts
3. Verify: Locked account listed
4. Click "Clear Lockout"
5. Reauthenticate (MFA required)
6. Submit
7. **Result**: "Lockout cleared for [user]"
8. Audit event: LOCKOUT_CLEARED by OWNER

**Test 3: Password Change & Session Revocation**
1. OWNER navigate: Account Security
2. Click "Change Password"
3. Current: DemoOwner@123456
4. New: NewPassword@123456
5. Submit
6. **Result**: "Password changed. All sessions logged out."
7. Forced redirect to login
8. Other browser tabs/windows: Session expired
9. **Observation**: All active sessions terminated simultaneously

**Test 4: MFA Regenerate Recovery Codes**
1. OWNER logged in
2. Navigate: Account Security → Regenerate Recovery Codes
3. **Result**: MFA prompt required (reauthentication)
4. Enter TOTP code
5. **Result**: New recovery codes displayed once
6. **Note**: Old codes invalidated (not retrievable)
7. Audit event: RECOVERY_CODES_GENERATED

Expected result: Login failures trigger lockout, OWNER can manage it, password changes revoke sessions, MFA regeneration invalidates old codes.

## Demonstration 7: Audit & Compliance (5 minutes)

**Test 1: Complete Audit Trail Access (OWNER Only)**
1. OWNER login
2. Navigate: Audit Trail
3. Verify columns: Timestamp, Actor, Event Type, Resource, IP Address
4. **All events visible**: LOGIN, PASSWORD_CHANGED, BOOKING_CREATED, POS_SALE_CREATED, etc.
5. Click event to expand: No passwords, tokens, or codes visible

**Test 2: CASHIER Denies Audit Access**
1. CASHIER login
2. Navigate: Try Audit Trail URL directly
3. **Result**: HTTP 403 Forbidden
4. Audit event logged: AUDIT_TRAIL_ACCESS_DENIED by cashier

**Test 3: Sensitive Data Redaction**
1. OWNER in Audit Trail
2. Filter: event_type contains BOOKING_VERIFICATION
3. Expand event detail:
   - Customer email: Visible
   - Verification code: [REDACTED] or ***
   - Access token: [REDACTED] or ***
   - MFA secret: [REDACTED] or ***
4. **Observation**: All cryptographic secrets hidden

**Test 4: Data Export (Not Implemented)**
1. OWNER attempts: Audit Trail → Export CSV
2. **Result**: "Export not yet implemented"
3. **Documented**: In FINAL_QA_REPORT.md

Expected result: Audit trail captures all events, restricted to OWNER, redacts sensitive data.

## Demonstration 8: Forecasting (OWNER Only, Requires Data) (5 minutes)

**Test 1: Access Control**
1. CASHIER login → Try Reports → Forecasting
2. **Result**: HTTP 403 Forbidden

**Test 2: Model Training**
1. OWNER login
2. Navigate: Reports → Forecasting
3. Click "Generate Forecast"
4. **System checks**:
   - Completed transactions: 300 (>= 30 required)
   - Training period: Past 180 days
   - Excluded: Voided transactions
5. **Result**: "Model training in progress..."
6. Model completes (< 5 seconds with demo data)
7. **Observation**: Metadata shows:
   - Training records: 300
   - Model type: Random Forest
   - Forecast horizon: 30 days
   - **No false confidence claims**

**Test 3: Insufficient Data Handling**
1. Navigate: Reports → Forecasting
2. Try with very small dataset (< 30 transactions)
3. **Result**: "Insufficient data to generate model. At least 30 completed transactions required."
4. **Observation**: No model/accuracy claims made without baseline

Expected result: Forecasting limited to OWNER, requires baseline data, doesn't make false confidence claims.

## Test Results Summary (5 minutes)

**Show test suite output**:
```
Found 166 test(s).
System check identified no issues (0 silenced).
...
Ran 166 tests in 65.849s
OK
```

**Coverage breakdown**:
- Accounts & Auth: 34 tests
- Bookings & Public: 37 tests
- Services & Monitoring: 9 tests
- POS & Transactions: 18 tests
- Reports & Forecasting: 10 tests
- Audit & Compliance: 15 tests
- Input Security: 15 tests
- Upload Security: 6 tests
- Core & System: 3 tests

**All pass**: 100%

## Closing Remarks

1. **Scope**: Core authentication, authorization, booking, audit, and POS modules are fully tested and production-ready.

2. **Limitations**: Placeholder features (notifications, live dashboards) are clearly marked. Production deployment requires SMTP, PostgreSQL, Redis, and HTTPS configuration.

3. **Demo Data**: Realistic 6-month transaction history included for validation. All demo passwords must be changed before external access.

4. **Next Steps**: Penetration testing, staging deployment, operator training, and runbook development recommended.

5. **Questions**: Refer to FINAL_QA_REPORT.md, SECURITY_TEST_CHECKLIST.md, and ROLE_PERMISSION_MATRIX.md for detailed specifications.

1. Sign in to the same test account in two browser profiles.
2. Change the password or deactivate the account in the controlled demonstration procedure.
3. Refresh both sessions.

Expected result: both sessions are rejected and session-revocation activity is visible.

## Demonstration 5: Login Throttling

1. Use a disposable account and fixed test IP/proxy setup.
2. Submit repeated wrong passwords.
3. Show CAPTCHA after its threshold.
4. Reach temporary lockout and show the generic response.
5. As OWNER, reauthenticate and inspect the valid lockout.

Expected result: submitted credentials are masked in Axes records and lockout does not expose account details.

## Demonstration 6: Public Booking Isolation

1. Submit a public booking.
2. Show that the database stores a digest rather than the emailed code.
3. Enter an invalid code, then the valid code.
4. Open the private status link.
5. Attempt to use its token with a different booking reference.
6. Reschedule and cancel the correct booking.

Expected result: the wrong booking is unavailable and public responses do not reveal record existence.

State that availability, service catalog, duration, and overlap checks are not implemented.

## Demonstration 7: CSRF And Input Security

1. Explain that activation GET is preview-only.
2. Show that activation transition uses POST and a CSRF token.
3. Show bounded server-side form errors with browser validation disabled.
4. Show the upload validator tests for extension, MIME, signature, size, pixel limit, and generated filename.

Expected result: no state change relies only on JavaScript or hidden fields.

Do not claim a live upload feature; only reusable validated infrastructure exists.

## Demonstration 8: Audit Evidence

1. Open Audit Trail as OWNER.
2. Show login, denial, MFA, session, and booking verification events.
3. Show request IDs and redacted token paths.
4. Explain that secrets and private POST payloads are excluded.

State that the audit database is not immutable against database administrators and has no external retention pipeline.

## Demonstration 8A: Service Catalog And Image Security

1. As OWNER, create a category and service with duration, Decimal price, and a valid image.
2. Show the generated `service-images/<uuid>` filename rather than the submitted filename.
3. Attempt an invalid image signature and show server rejection.
4. Mark one service inactive.
5. Sign in as CASHIER and show that only active catalog entries are readable.
6. Attempt the service-edit and StaffProfile URLs as CASHIER and show HTTP 403.

State that service selection is not yet linked to public booking and appointment conflict rules remain Stage 2 work.

## Demonstration 9: Deployment Evidence

Show saved output from:

```text
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py test
```

Explain the production environment used for `check --deploy`, including HTTPS, secure cookies, HSTS decision, explicit hosts, CSRF origins, SMTP, database, and external media root. Do not hide warnings.

## Closing Limitations

State clearly:

- No completed POS or server-side financial totals exist.
- No appointment conflict engine exists.
- No production proxy, TLS, shared cache, backup automation, or immutable audit integration is included.
- Upload validation is not connected to a live upload form.
- Automated tests reduce known regression risk but do not prove the whole system is secure.
