# Get Nailed - OpenCode Development Prompts (Owner, Cashier, Staff, Customer)

Use **one stage at a time**. Prepend the Master Rules to every stage. Commit only after tests pass.

## Master Rules

```text
You are extending an existing Django 5.2 LTS capstone project for Get Nailed Nail Bar and Spa. Preserve the current architecture, official circular logo, theme variables, custom accounts.User model, role-based dashboards, and existing URLs unless a migration-safe change is required. Do not rebuild working modules. Use Django best practices, database transactions for financial operations, Decimal for money, server-side validation, object-level authorization, timezone-aware datetimes using Asia/Manila, accessible responsive templates, automated tests, and clear audit logging. The application roles are OWNER, CASHIER, STAFF, and optional CUSTOMER. Public customers may book without an account. STAFF permissions are fine-grained: POS, booking management, customer management, and service assignment can be granted by OWNER. CASHIER has the implemented operational capability set but never receives owner-only financial reports, forecasting controls, audit logs, security settings, or user-management features. Use only the circular Get Nailed logo. Keep all features aligned with the approved capstone scope: single branch, local payment recording only, no third-party payment gateway, no payroll/ERP/procurement/loyalty/SMS/email-marketing integrations, and AI limited to Random Forest service-sales forecasting. Before changing code, inspect existing models/URLs/templates and report migration risks. After each stage, report changed files, migration commands, test commands, test results, and manual acceptance checks. Do not claim completion unless tests pass.
```

## Stage 0A — Authentication and email verification
```text
Inspect the existing authentication foundation first. Implement secure email-and-password authentication using the existing custom User model. Normalize and uniquely enforce email. OWNER/CASHIER/STAFF accounts have no public registration; only OWNER creates CASHIER or STAFF accounts. Add secure single-use expiring account activation and verified-email requirement before internal login. New internal users set their own password through activation; never store or email plaintext passwords. Configure Argon2 as preferred hasher plus Django password validators. Add password change, forgot/reset password, generic anti-enumeration messages, session invalidation after password change/reset/deactivation, console email in development and environment-based SMTP in production. Add branded templates using only the circular logo. Tests: email uniqueness, activation expiration/reuse, unverified/inactive login rejection, password hashing/validation/reset, anti-enumeration, session invalidation. Create SECURITY_ARCHITECTURE.md and AUTHENTICATION_FLOW.md; update .env.example, requirements.txt, README.md. Run makemigrations, migrate, check, test.
```

## Stage 0B — MFA and account recovery
```text
Continue from working Stage 0A. Implement TOTP authenticator-app MFA with recovery codes using a maintained Django 5.2-compatible solution. MFA is mandatory for OWNER and configurable for CASHIER/STAFF. Require verified email before enrollment. Recovery codes must be hashed, single-use, shown only when generated, and invalidated on regeneration. Require recent password + MFA reauthentication before disabling MFA, resetting MFA, or regenerating recovery codes. Invalidate sessions after MFA reset. Audit MFA security events without logging OTPs/secrets/codes. Add tests for OWNER MFA enforcement, CASHIER/STAFF configuration, invalid TOTP, used recovery codes, regeneration, and session invalidation. Create MFA_RECOVERY_GUIDE.md.
```

## Stage 0C — Login, lockout, and session protection
```text
Implement login throttling and temporary lockout using a maintained Django 5.2-compatible package such as django-axes. Start with 5 failed attempts and 15-minute configurable cooldown. Add OWNER lockout review/unlock. Avoid permanent lockouts and account enumeration. Use secure database-backed sessions, rotate sessions after authentication/privilege changes, flush on logout, inactivity timeout (OWNER 30 min, CASHIER/STAFF 60 min configurable), logout current/all devices, revoke sessions on password reset, account deactivation, role/permission change, and MFA reset. Prevent open redirects. Separate development/production security settings and configure secure cookies, CSRF, HTTPS redirect, HSTS only after HTTPS is confirmed, ALLOWED_HOSTS, trusted origins, framing/referrer/nosniff protections. Add tests and run check --deploy.
```

## Stage 0D — Role permissions and sensitive-action reauthentication
```text
Implement reusable server-side authorization for OWNER, CASHIER, STAFF, CUSTOMER/anonymous. OWNER has full administration. CASHIER has the approved operational capability set without owner administration. STAFF has fine-grained booleans/permissions for POS, booking management, customer management, and service assignment; otherwise STAFF sees only personal profile, assigned work, schedule, allowed status updates, and notifications. CUSTOMER/anonymous only public booking-related functions. Enforce permissions in views, forms, services and querysets, not only menus. Add object-level authorization and 403 handling. Prevent deactivation/removal of final active OWNER. Require recent password + MFA reauthentication for role/permission changes, account deactivate/reactivate, MFA reset, completed-sale void, full audit export, security settings, and sensitive deletion. Add tests for direct URL access and ID tampering. Create ROLE_PERMISSION_MATRIX.md.
```

## Stage 1 — Services, staff profiles, schedules, and permissions
```text
Implement ServiceCategory, Service, StaffProfile, StaffSchedule, StaffTimeOff, and optional SalonClosure. Service: name, category, description, duration_minutes, price, active, image, timestamps. StaffProfile links one-to-one to STAFF user and stores specialty, availability, active state. OWNER CRUD; STAFF read only as authorized. Owner can grant fine-grained operational permissions: can_use_pos, can_manage_bookings, can_manage_customers, can_assign_services. Add business-hours and day-off rules used by booking availability. Validate uploads, paginate/search/filter, polished branded UI, admin, realistic fixtures, tests.
```

## Stage 2 — Customers, smart booking, verification, and tracking
```text
Implement Customer, Appointment, AppointmentService, and booking verification/access-token models. Appointment includes non-sequential booking_reference, customer, services, date/start/end, assigned_staff, source (PUBLIC/WALK_IN/STAFF), status including UNVERIFIED/PENDING/APPROVED/RESCHEDULED/WAITING/ONGOING/COMPLETED/CANCELLED/REJECTED/NO_SHOW, notes/reasons, created_by, timestamps. Build polished public multi-step booking without login. Calculate available slots from salon hours, closures, service duration, staff schedules/time-off, existing bookings, configurable buffer, and advance-booking window. Prevent overlaps and past/closed times server-side. Public bookings remain UNVERIFIED until single-use expiring email code/signed-link verification; throttle resend/attempts. Secure booking tracking/cancel/reschedule requires reference + verified access and must authorize only that booking. OWNER and permitted STAFF manage calendar/list/approval/assignment; assigned STAFF update only valid status transitions. Notifications for creation, verification, approval, rejection, reschedule, cancellation, reminder. Tests for scheduling conflicts, token isolation, expiry/reuse, enumeration resistance, permissions, transitions.
```

## Stage 3 — Production-style salon POS, receipts, and discounts
```text
Implement Sale, SaleItem, Payment, ReceiptSequence, Discount/DiscountApplication as appropriate. Support walk-ins and linked appointments, multiple services, staff per item, immutable captured service name/price, subtotal, percentage/fixed/promo discount with reason and applied_by, total, tendered, change, local payment method, status, void reason/approval, processor, timestamps, immutable receipt number. Use transaction.atomic + Decimal. Server calculates all totals; never trust browser prices. Prevent negative totals/insufficient cash and duplicate completion. Completed sales feed reports/forecasting and may complete linked appointment. Build touch-friendly category/service-card POS with order panel and branded printable receipt using circular logo. OWNER-only or reauthenticated owner approval for voids and unusual discounts. Transaction history and staff shift/daily summary only when permitted. Tests for totals, discounts, change, receipt uniqueness, concurrency/rollback, void authorization, immutable historical values.
```

## Stage 4 — Real-time service operations board
```text
Implement HTMX-polled service board with WAITING, ONGOING, COMPLETED plus relevant pending/approved queue. Show customer, service, assigned staff, start/expected finish, lateness indicator. STAFF sees assigned work unless granted assignment permission. OWNER/permitted STAFF can assign/reassign. Enforce valid transition graph and create ServiceStatusHistory(old,new,user,time,note). Add workload counters, today's queue, filters, responsive Kanban UI, audit events, tests.
```

## Stage 5 — Live dashboards, reports, exports, and notifications
```text
Replace placeholders with live role-aware dashboards. OWNER: today's sales, appointments, completed/ongoing services, pending bookings, customers, top services, top staff by completed count, recent transactions, sales trend, appointment timeline, service queue. STAFF: only allowed operational KPIs, today's assigned work, schedule, notifications; sensitive financial cards hidden unless explicitly permitted and never owner-level reports. Reports: daily/weekly/monthly/annual sales, service sales, appointment status, staff workload; only completed non-voided sales. Add consistent date filters and CSV/XLSX/branded PDF exports. Notification center with unread/read/all, booking/service/security events. Tests ensure dashboard totals equal reports and permissions hold.
```

## Stage 6 — Defensible Random Forest forecasting
```text
Implement KDD-style forecasting from completed non-voided Sale/SaleItem only: extraction, cleaning, feature creation, train/evaluate/predict/persist. RandomForestRegressor. Use date/day/weekend/month, lag/rolling features only when enough data, category/service aggregates, transaction count and service-sales totals. Add ForecastRun/ForecastResult storing dataset range/count, parameters, MAE, RMSE, R2, MAPE only when valid, generated forecasts, artifact path/version. OWNER-only train/evaluate/generate/compare/export. UI must show historical vs forecast chart, forecast by service/category, model metadata/metrics, data range/record count, and honest INSUFFICIENT DATA state. Never fabricate accuracy. Add a carefully worded 'Model indicators contributing to forecast' section using feature importance/observable signals, never causal claims. Forecast is decision support, not autonomous decisions. Deterministic synthetic-data tests.
```

## Stage 7 — Audit, backup guidance, system health, accessibility, and hardening
```text
Complete structured audit logging for login/logout/failures/lockouts, account/permission changes, booking decisions, POS completion/discount/void, service status changes, exports, forecast train/generate, MFA/session security events. Search/filter and owner-only CSV/PDF export; never log secrets/tokens/session IDs/OTP values. Add safe System Health page for OWNER showing application/database/email configuration status, last backup metadata, model availability, failed-login alert count and version without secrets. Add backup/restore documentation and management commands or scripts appropriate for PostgreSQL; do not expose dangerous restore in ordinary UI. Harden CSRF, uploads, object authorization, headers, error pages (403/404/500), accessible labels/keyboard navigation, responsive empty/loading/error states. Add security regression tests.
```

## Stage 8 — Final integration, seed data, evaluation evidence, and defense readiness
```text
Do not redesign/rebuild. Perform end-to-end QA across Accounts, Services, Customers, Bookings, POS, Monitoring, Reports, Forecasting, Notifications, Audit. Verify fresh migrations, URLs/templates/static/media, cross-module workflow: public booking -> verify -> approve -> assign -> waiting/ongoing/completed -> POS -> receipt -> dashboard/report -> forecasting dataset. Also test walk-in and cancel/reject/reschedule/no-show/void flows. Verify Asia/Manila, concurrency, appointment overlaps, duration/buffers, permissions, report consistency, forecast data eligibility, insufficient-data handling. Seed realistic demo data: 1 OWNER, CASHIER accounts as needed, 5-10 STAFF with varied permissions, 50 customers, 150 appointments, 300+ transactions spanning enough historical months, notifications and audit events; no plaintext production passwords. Update DEPLOYMENT.md, USER_MANUAL.md, DEFENSE_DEMONSTRATION_SCRIPT.md, ROLE_PERMISSION_MATRIX.md, SECURITY_TEST_CHECKLIST.md, and the other approved security documents. Future outputs such as a database backup guide and ISO 25010 evidence checklist must be created only when their controls are implemented. Record real test counts and measured performance only; never invent values. Run the full test suite and check --deploy; document known limitations.
```

## Defense demo sequence
```text
1. OWNER login + MFA.
2. Show role/permission management.
3. Submit and verify a public booking.
4. Approve and assign staff.
5. Show staff schedule and service board; move through valid statuses.
6. Process POS payment and print receipt.
7. Show dashboard/report totals updated consistently.
8. Show forecast page with data range, metrics, historical-vs-forecast, and insufficient-data behavior where relevant.
9. Show audit trail.
10. Demonstrate security: STAFF manually opens an OWNER-only URL and receives 403.
11. Show system health and backup documentation.
```
