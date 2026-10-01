# Stage 5 Reports And Dashboard Report

Date: 2026-07-23

## Implemented Scope

- Shared report/KPI query layer used by dashboards, HTML reports, and exports.
- Every financial query begins with completed sales and therefore excludes voided transactions.
- OWNER dashboard with today's net sales and transaction count, verified customer count, verified appointment count, current ongoing services, top services, top staff by completed service count, recent completed transactions, and a seven-day sales trend.
- CASHIER dashboard with cashier-scoped completed POS totals, discounts, transaction list, today's verified bookings, and pending-booking count.
- STAFF dashboard with today's assigned service work, ongoing/completed counters, unread notification count, and recent notifications.
- Daily, weekly, monthly, and annual completed-sales reports.
- Service sales report using immutable `SaleItem` service snapshots from completed sales.
- Appointment status report using verified appointment records.
- Staff workload report with assigned, completed, ongoing, and scheduled-minute totals.
- Validated start/end date filters with a maximum ten-year range.
- CSV exports with UTF-8 BOM and spreadsheet-formula injection protection.
- Styled XLSX exports with branded headings, frozen headers, and fitted columns.
- Branded landscape PDF exports using the circular Get Nailed logo and repeating table headers.
- OWNER-only access to full reports and all export formats.
- Existing OWNER/CASHIER daily cashier closeout retained, with CASHIER data scoped to their own sales.
- Responsive dashboard KPI, ranking, trend, transaction, notification, and report navigation components.

## Financial Scope

The following use only `Sale.status=COMPLETED` records:

- Today's OWNER and CASHIER sales KPIs.
- Sales trend.
- Top services by sold quantity and gross item revenue.
- Recent dashboard transactions.
- Daily, weekly, monthly, and annual sales reports.
- Service sales reports.
- Daily cashier summaries and payment breakdowns.
- CSV, XLSX, and PDF financial exports.

Voided sales remain in immutable POS history but do not contribute to these totals.

Appointment-status and staff-workload reports are operational reports and do not calculate financial totals.

## Files And Areas

- Shared report and dashboard queries: `apps/reports/services.py`
- Export generators: `apps/reports/exports.py`
- Date filters: `apps/reports/forms.py`
- Report views and role enforcement: `apps/reports/views.py`
- Report routes: `apps/reports/urls.py`
- Dashboard context wiring: `apps/core/views.py`
- Owner/CASHIER/STAFF dashboards: `templates/dashboards/`
- Report pages: `templates/reports/`
- Report value formatting: `apps/reports/templatetags/report_tags.py`
- Responsive dashboard/report styling: `static/css/app.css`
- Tests: `apps/reports/tests.py`

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 160 tests passed in 49.998 seconds |
| Reports/dashboard tests | 9 passed in 5.199 seconds |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

Stage 5 required no database migration because it reports against the historical models introduced in Stages 2 through 4.

## Tested Behaviors

- Exact completed-sale totals across daily, weekly, monthly, and annual reports.
- Voided sales and their items excluded from all financial report totals.
- Service sales use only completed, non-voided item snapshots.
- Appointment status and staff workload calculations.
- OWNER KPI, ranking, transaction, and trend values.
- CASHIER totals and transaction lists scoped to that cashier.
- STAFF assigned work and unread notifications.
- Date-filtered rendering of all seven report types.
- CSV, XLSX, and branded PDF response signatures, content types, and attachments.
- Full report pages and exports denied to CASHIER, STAFF, and CUSTOMER roles.

## Deferred Work

- Sales trends are descriptive historical totals, not forecasts. Forecasting remains a separate module.
- Service sales report gross item revenue before sale-level discounts because discounts are stored at sale level and are not allocated across items.
- Taxes, cost of goods, commissions, tips, refunds, split payments, and profit/margin reporting are not modeled.
- Dashboard queries run live. Scheduled aggregates, caching, and a reporting warehouse may be needed at larger data volumes.
- Exports are generated synchronously. Large production exports may need background jobs and expiring download storage.
- PDF uses built-in ReportLab fonts; custom brand-font embedding and localization are not included.
- Reports follow the configured `Asia/Manila` application timezone and do not provide per-user timezone selection.

This report covers Stage 5 dashboards and reports only. It does not claim completion of predictive forecasting, accounting, tax compliance, inventory analytics, or external business-intelligence integrations.
