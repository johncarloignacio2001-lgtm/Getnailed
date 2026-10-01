# Capstone Improvement Plan

This foundation already contains the Django project structure, branding, custom user model, role dashboards, and placeholder apps. The advanced features below are **planned, not yet fully implemented**. Implement them through `OPENCODE_PROMPTS.md` one stage at a time.

## Highest-priority improvements

1. Keep the implemented roles consistent everywhere: OWNER, CASHIER, STAFF, and optional CUSTOMER.
2. Fine-grained STAFF permissions for POS, bookings, customers, and service assignment.
3. Smart appointment availability based on business hours, staff schedules, time off, service duration, buffers, closures, and conflicts.
4. Secure public booking verification and tracking.
5. Touch-friendly salon POS with transactional integrity, immutable receipts, discount controls, void approval, and historical snapshots.
6. Real-time service Kanban with valid state transitions and status history.
7. Live owner dashboard and reports whose totals reconcile exactly.
8. Defensible Random Forest forecasting with metrics, data provenance, honest insufficient-data handling, feature indicators, and decision-support wording.
9. MFA, lockout, session revocation, object-level authorization, reauthentication, audit logging, upload security.
10. Demo seed data, system-health page, backup/restore guide, ISO 25010 evidence checklist, and a scripted defense flow.

## Scope guardrails
Do not add third-party payment gateways, payroll, ERP, procurement, loyalty/rewards, SMS, email marketing, multi-branch management, or unrelated AI features unless the approved manuscript is formally revised.
