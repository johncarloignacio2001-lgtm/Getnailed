# Stage 4 Service Monitoring Report

Date: 2026-07-23

## Implemented Scope

- Individual `AppointmentService` rows now act as operational service work items.
- Independent PENDING, APPROVED, ONGOING, and COMPLETED state per service in a multi-service appointment.
- Per-service staff assignment, approval/start/completion timestamps, and expected finish timestamp.
- Transactional `ServiceStatusHistory` with user, timestamp, old status, new status, and optional note for every service transition.
- Strict manager transitions: `PENDING -> APPROVED -> ONGOING -> COMPLETED`.
- Strict assigned-STAFF transitions: `APPROVED -> ONGOING -> COMPLETED`.
- STAFF board/query access restricted to their assigned work.
- OWNER and CASHIER can assign or reassign visible services.
- Existing explicit `can_assign_services` grants remain supported, but direct object access stays scoped to visible work.
- Parent appointment status synchronized from all child service states.
- Existing appointment-management and POS completion transitions synchronize service states and histories.
- Existing appointment-level assignment updates synchronize service assignments.
- HTMX board polling every 10 seconds using standard Django fragment responses.
- Separate Pending, Approved, Ongoing, and Completed columns.
- Workload counters per active staff member for pending, ready, and active services.
- Date, staff, service, customer, and booking-reference filters.
- Today's queue count, scheduled time, expected finish, and late indicators.
- Responsive branded horizontal board for desktop, tablet, and mobile screens.
- Structured `SERVICE_STATUS_CHANGED` and `SERVICE_ASSIGNED` audit/security events in addition to request audit logs.
- OWNER-only read-only admin access to service status history.
- Unverified, cancelled, rejected, no-show, and expired appointments excluded from the live board.

## Files And Areas

- Operational service fields: `apps/bookings/models.py`
- Appointment and POS synchronization: `apps/bookings/services.py`, `apps/pos/services.py`
- Transition and assignment service layer: `apps/monitoring/services.py`
- Status history: `apps/monitoring/models.py`
- Filters and assignment forms: `apps/monitoring/forms.py`
- Board, polling, and mutation views: `apps/monitoring/views.py`
- Routes: `apps/monitoring/urls.py`
- Templates: `templates/monitoring/`
- Responsive board styling: `static/css/app.css`
- Tests: `apps/monitoring/tests.py`
- Audit actions: `apps/audittrail/models.py`

## Migrations

- `audittrail.0004_alter_securityevent_action`
- `bookings.0005_appointmentservice_approved_at_and_more`
- `bookings.0006_initialize_service_monitoring`
- `monitoring.0001_initial`

The data migration initializes existing service staff assignments and operational states from their parent appointments. Existing completed and ongoing services also receive best-available historical timestamps and expected finish estimates without inventing transition-history events that did not occur.

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 151 tests passed in 45.907 seconds |
| Monitoring tests | 8 passed in 3.484 seconds |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

All Stage 4 migrations are applied to the working database.

## Tested Behaviors

- STAFF sees only assigned service work.
- Unverified appointment services remain hidden.
- Invalid, skipped, and cross-staff transitions are rejected.
- Every valid transition records complete status history.
- Multi-service state changes synchronize the parent appointment correctly.
- Assignment requires capability and updates the appointment-level assignment summary when all services match.
- Status and assignment HTTP actions produce structured audit events.
- HTMX polling returns fragments rather than full page documents.
- Workload counters, staff/date/text filters, expected finish, and late indicators render correctly.
- Existing appointment status decisions synchronize all child service states.

## Deferred Work

- Polling is fixed at 10 seconds; WebSockets, server-sent events, and push notifications are not included.
- HTMX is loaded from a pinned public CDN URL. Production deployments may choose to self-host it for offline operation and tighter supply-chain control.
- Monitoring currently tracks appointment service rows. Standalone walk-in work without an appointment is retained in POS history but is not a live monitoring work item.
- Breaks, station/chair allocation, staff time-off calendars, pause/resume, service handoff, and queue drag-and-drop are not modeled.
- Expected finish is duration-based. It does not use predictive delay models or automatically reschedule later appointments.
- Database row locking is implemented, but production concurrency testing should run against the deployed transactional database rather than relying only on SQLite tests.

This report covers Stage 4 service monitoring only. It does not claim completion of inventory, payroll, advanced forecasting, or external real-time infrastructure.
