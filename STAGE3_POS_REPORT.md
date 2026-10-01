# Stage 3 Point Of Sale Report

Date: 2026-07-23

## Implemented Scope

- Transactional `Sale`, `SaleItem`, `Payment`, and `ReceiptSequence` models.
- Globally increasing, unique, immutable receipt numbers in `GN-YYYYMMDD-NNNNNNNN` format.
- Seeded singleton receipt sequence locked during checkout so sequence changes roll back with failed sales.
- Walk-in customers, saved customers, and one-to-one appointment checkout support.
- Multiple canonical services per sale with quantity and assigned STAFF per item.
- Immutable service, unit-price, staff, customer, and cashier snapshots for historical reporting.
- Decimal-only subtotal, fixed/percentage discount, discount amount, total, tendered amount, and change calculations.
- Cash sufficiency checks and exact-value validation for locally recorded non-cash methods.
- Database constraints for nonnegative values, component-total equality, valid status/payment/discount choices, non-cash change, and complete void metadata.
- Atomic linked-appointment completion with status history.
- Touch-oriented checkout with six service rows, appointment prefill, customer selection, staff assignment, live total preview, and large payment controls.
- Printable receipt using the circular Get Nailed logo and print-specific 80 mm styling.
- Cashier-scoped transaction history and receipt access; OWNER can view all transactions.
- OWNER-only void review with recent reauthentication and mandatory reason.
- Voids preserve receipt, item, and payment history while excluding the transaction from completed-sales totals.
- Daily cashier summary with gross subtotal, discounts, net sales, void count, payment-method breakdown, and completed transaction detail.
- Read-only OWNER admin visibility for sales and the receipt sequence.

## Files And Areas

- Models and constraints: `apps/pos/models.py`
- Transaction and void services: `apps/pos/services.py`
- Checkout/history/void forms: `apps/pos/forms.py`
- POS views and routes: `apps/pos/views.py`, `apps/pos/urls.py`
- Daily summary: `apps/reports/forms.py`, `apps/reports/views.py`
- POS and receipt templates: `templates/pos/`
- Daily report template: `templates/reports/daily_summary.html`
- Responsive and receipt styling: `static/css/app.css`
- Tests: `apps/pos/tests.py`
- Migrations: `apps/pos/migrations/0001_initial.py`, `apps/pos/migrations/0002_seed_receipt_sequence.py`

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 143 tests passed in 41.572 seconds |
| POS tests | 11 passed |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

`pos.0001_initial` and `pos.0002_seed_receipt_sequence` are applied to the working database.

## Tested Behaviors

- Fixed and percentage totals.
- Cash change and exact non-cash payments.
- Negative/excessive discounts and insufficient cash rejection.
- Receipt uniqueness and immutability.
- Capability and owner-only void permissions.
- Historical snapshots after catalog changes.
- Appointment completion and status history.
- Full rollback of receipt sequence, sale, items, payment, and appointment status after payment persistence failure.
- Database rejection of negative totals.
- Checkout, receipt, transaction history, daily summary, and cashier receipt scoping.
- Voided-sale retention and completed-sales exclusion.

## Deferred Work

- Payment methods are local records only; no card, bank, GCash, or Maya gateway is contacted or verified.
- Refunds, partial payments, split tender, taxes, tips, gift cards, and chargeback workflows are not included.
- Cash drawer opening balances, shift close/reconciliation, and physical printer/drawer integrations are not included.
- Inventory/product sales are outside this service-focused POS stage.
- Receipt delivery by email or SMS is not included.
- Row-lock behavior is implemented for transactional databases; production concurrency validation should also run against the deployed PostgreSQL/MySQL database rather than relying only on SQLite tests.
- Forecasting can consume completed historical `Sale` and `SaleItem` records, but forecasting models and projections remain a later stage.

This report covers Stage 3 POS only. It does not claim payment processor compliance, fiscal-device certification, accounting-ledger completeness, or completion of later reporting and forecasting stages.
