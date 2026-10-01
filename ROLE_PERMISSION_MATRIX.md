# Role Permission Matrix

This is the current implemented authorization model. Several permitted business routes remain placeholders and permission to open a route does not imply that its planned workflow exists.

| Capability | OWNER | CASHIER | STAFF default | STAFF granted | CUSTOMER | Public |
|---|---:|---:|---:|---:|---:|---:|
| Owner dashboard | Yes | No | No | No | No | No |
| Staff dashboard | Yes | Yes | Yes | Yes | No | No |
| Customer dashboard | No | No | No | No | Yes | No |
| Internal invitations | Yes | No | No | No | No | No |
| MFA policy and lockouts | Yes + reauth | No | No | No | No | No |
| Service catalog read | Yes | Yes | No | No | No | No |
| Category/service CRUD | Yes + delete reauth | No | No | No | No | No |
| Staff profile management | Yes + delete reauth | No | No | No | No | No |
| POS route | Yes | Yes | No | `can_use_pos` | No | No |
| Booking management | Yes | Yes | No | `can_manage_bookings` | No | No |
| Assigned appointments | All | No | Assigned only | Assigned only | No | No |
| Customer-record route | Yes | Yes | No | `can_manage_customers` | No | No |
| Monitoring route | Yes | Yes | Yes | Yes | No | No |
| Service-assignment route | Yes | Yes | No | `can_assign_services` | No | No |
| Daily summary route | Yes | Yes | No | No | No | No |
| Full reports | Yes | No | No | No | No | No |
| Forecasting | Yes | No | No | No | No | No |
| Audit trail | Yes | No | No | No | No | No |
| Void approval route | Yes | No | No | No | No | No |
| Notifications route | Yes | Yes | Yes | Yes | Yes | No |
| Public booking creation | Yes | Yes | Yes | Yes | Yes | Yes |
| Booking status/cancel/reschedule | Valid token | Valid token | Valid token | Valid token | Valid token | Valid token |

## Capability Rules

- OWNER or superuser bypasses operational capability checks.
- CASHIER intrinsically receives POS, booking management, customer management, assignment, monitoring, and daily-summary capabilities.
- CASHIER receives read-only service catalog access but cannot create, edit, or delete catalog or staff-profile records.
- STAFF intrinsically receives monitoring and assigned-booking access.
- STAFF can receive `can_use_pos`, `can_manage_bookings`, `can_manage_customers`, and `can_assign_services`.
- CUSTOMER receives no internal operational capability.
- Public booking access is based on a verified booking reference and bearer token, not account role.

## Enforcement

- Views use server-side decorators and mixins.
- Object IDs must be resolved through role-scoped querysets.
- Browser-supplied role names, hidden fields, query strings, user IDs, and menu visibility are not authorization decisions.
- Anonymous users are redirected to login for protected routes.
- Authenticated but unauthorized users receive HTTP 403 and create an unauthorized-access security event.

## Current Limitations

- There is no normal application UI for editing roles or fine-grained capabilities; StaffProfile stores operational metadata only.
- Final-owner protection is not implemented.
- CUSTOMER accounts are not linked to a customer-owned booking queryset; public booking access remains token-based.
- POS, monitoring, reports, forecasting, and notification business functions are placeholders.
