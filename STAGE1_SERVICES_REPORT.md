# Stage 1 Services And Staff Profiles Report

Date: 2026-07-23

## Implemented Scope

- `ServiceCategory` with case-insensitive unique names, description, and timestamps.
- `Service` with category, description, 5-480 minute duration, positive Decimal price, active state, validated image, and timestamps.
- `StaffProfile` linked one-to-one to an existing STAFF account with specialty, availability status, active state, and timestamps.
- OWNER-only category, service, and staff-profile create/update/delete workflows.
- Recent reauthentication for deletion.
- OWNER and CASHIER read-only catalog access; CASHIER sees active services only.
- Server-side search, category/status/availability filters, and pagination.
- JPEG, PNG, and WebP signature/MIME/extension/size/pixel validation.
- UUID service-image filenames and post-commit replacement/deletion cleanup.
- Cleanup of newly stored files after failed database persistence.
- Prevention of account role changes that would leave an invalid StaffProfile.
- OWNER-only admin registrations with admin deletion disabled in favor of reauthenticated application deletion.
- Responsive branded service cards and management tables.
- A realistic five-category salon fixture with at least fifteen services and Philippine peso pricing.

## Files And Areas

- Models: `apps/services/models.py`
- Forms and filters: `apps/services/forms.py`
- Views and authorization: `apps/services/views.py`
- URLs: `apps/services/urls.py`
- Image cleanup and role-integrity signals: `apps/services/signals.py`
- Admin: `apps/services/admin.py`
- Fixture: `apps/services/fixtures/stage1_catalog.json`
- Tests: `apps/services/tests.py`
- Templates: `templates/services/`
- Navigation and responsive styling: `templates/partials/sidebar.html`, `static/css/app.css`
- Migration: `apps/services/migrations/0001_initial.py`

## Verification

| Check | Result |
|---|---|
| `python manage.py test` | 123 tests passed in 31.088 seconds |
| Services tests | 17 passed |
| `python manage.py check` | 0 issues, 0 silenced |
| Production-profile `python manage.py check --deploy` | 0 issues, 0 silenced |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py migrate --check` | No pending migrations |
| `python -m pip check` | No broken requirements |
| `python -m compileall -q apps config` | Passed |

`services.0001_initial` is applied.

## Optional Demo Data

Load the fixture into an empty development or demonstration catalog:

```text
python manage.py loaddata stage1_catalog
```

The fixture was validated by automated tests. It was not loaded into the working database automatically, avoiding unexpected replacement or duplication of local catalog data.

## Manual Acceptance Checks

1. Sign in as OWNER and create a category and service.
2. Upload a valid JPEG, PNG, or WebP and confirm a UUID filename under `service-images/`.
3. Attempt a mismatched or corrupt image and confirm server rejection.
4. Search by service name/description and combine category/status filters.
5. Create enough records to verify filter-preserving pagination.
6. Mark a service inactive and confirm OWNER still sees it while CASHIER does not.
7. Confirm CASHIER cannot open create, edit, delete, category-management, or StaffProfile routes.
8. Create a StaffProfile for an existing STAFF account.
9. Confirm OWNER, CASHIER, and CUSTOMER accounts cannot be selected for StaffProfile.
10. Confirm deleting a StaffProfile leaves the account intact.
11. Confirm category deletion is blocked while services reference it.
12. Confirm deletion prompts require recent reauthentication.
13. Replace and delete a service image and confirm old files are removed.

## Deferred Work

- Public booking still stores free-text service names and does not select from the new catalog.
- Appointment duration, business hours, staff schedules, time off, capacity, and overlap prevention remain Stage 2 work.
- StaffProfile availability is an operational manual status, not calculated appointment availability.
- Service prices are catalog values only; POS sale snapshots and server-calculated totals are not implemented.
- Images are validated but not re-encoded, metadata-stripped, or malware-scanned.
- Media storage remains outside the database transaction and requires coordinated backup and orphan monitoring in production.

The implemented Stage 1 scope is tested and working, but this is not a claim that later booking, POS, reporting, or production-infrastructure stages are complete or secure.
