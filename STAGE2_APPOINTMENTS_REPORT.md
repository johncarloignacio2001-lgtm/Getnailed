# Stage 2 Customers And Appointments Report

Date: 2026-07-23

## Implemented Scope

- Canonical `Customer`, `Appointment`, `AppointmentService`, `AppointmentStatusHistory`, and `Notification` records.
- Case-insensitive customer email identity with normalized contact details and management notes.
- Four-step anonymous booking flow for contact details, active canonical services, schedule/staff preference, and review.
- Existing hashed OTP verification, attempt limits, resend controls, hashed access tokens, expiry, cancellation, rescheduling, and generic failure responses preserved for appointments.
- Unverified and expired appointment/customer data excluded from internal management surfaces.
- Immutable service name, duration, price, and display-order snapshots on each appointment.
- Server-calculated end times from the total selected service duration.
- Transactional staff/profile locking and intersection-based overlap rejection for active appointment states.
- OWNER/CASHIER appointment list, filters, calendar, details, assignment, rescheduling, approval, rejection, cancellation, and status history.
- Existing explicit STAFF booking-management grants remain supported, with appointment rows still restricted to that staff member's assignments.
- STAFF-only assigned list and restricted `APPROVED/RESCHEDULED -> ONGOING/NO_SHOW` and `ONGOING -> COMPLETED` transitions.
- In-app notifications for new verified requests, assignment, schedule changes, and status decisions.
- Customer email updates for management schedule and status decisions.
- Searchable customer list, editable contact/notes detail, and verified appointment history.
- Additive migration of legacy bookings to appointments without deleting the legacy rows.
- Legacy free-text booking endpoints and list rendering retained as a narrow compatibility path.
- OWNER-only, non-destructive admin visibility for canonical appointments and customers.

## Migrations

- `customers.0001_initial`
- `bookings.0003_appointment_appointmentservice_and_more`
- `bookings.0004_copy_legacy_bookings`
- `notifications.0001_initial`

Legacy status mapping:

- `UNVERIFIED -> UNVERIFIED`
- `CONFIRMED -> PENDING`
- `CANCELLED -> CANCELLED`
- `EXPIRED -> EXPIRED`

Legacy free-text services receive a historical 60-minute, zero-price snapshot and `requires_schedule_review=True`. This avoids inventing a catalog match or price and requires management review before normal scheduling.

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 132 tests passed in 37.104 seconds |
| Canonical appointment workflow tests | 9 passed |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

All Stage 2 migrations are applied to the working database.

## Deferred Work

- The legacy `Booking` table and compatibility request path remain during the expand/migrate/cutover period. Removal requires a separately verified cleanup migration after deployed consumers have moved to canonical appointments.
- Business opening hours, recurring staff schedules, time off, holidays, and multi-seat capacity are not modeled. Current conflict prevention protects assigned staff from overlapping active appointments.
- The public scheduler validates availability at final submission rather than presenting a precomputed slot inventory.
- Walk-in and staff-created source values exist in the schema, but dedicated creation screens are not part of this stage.
- Notification delivery is synchronous; a production task queue and retry/dead-letter policy remain infrastructure work.
- Calendar rendering is a responsive schedule view, not a drag-and-drop calendar.

This report covers Stage 2 customers and appointments only. It does not claim completion of POS, payments, reporting, forecasting, or production infrastructure.
