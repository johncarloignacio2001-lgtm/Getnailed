# Security Test Checklist

Run the complete suite with `python manage.py test`. This checklist maps required controls to automated evidence. A passing test validates the tested behavior only; it does not establish production security.

## Required Automated Tests

| Requirement | Automated evidence |
|---|---|
| Verified email required for internal login | `AuthenticationSecurityTests.test_internal_login_requires_a_verified_email` |
| Invalid verification code | `PublicBookingSecurityTests.test_verification_attempt_limit_and_expiry_are_enforced` |
| Expired verification code | `PublicBookingSecurityTests.test_expired_verification_code_is_rejected_while_booking_remains_available` |
| Maximum booking OTP attempts | `PublicBookingSecurityTests.test_verification_attempt_limit_and_expiry_are_enforced` |
| Maximum MFA attempts | `MFASecurityTests.test_mfa_attempt_limit_temporarily_rejects_further_codes` |
| One-time activation token | `AuthenticationSecurityTests.test_activation_sets_password_verifies_email_and_is_single_use` |
| Password hashing | `AuthenticationSecurityTests.test_login_uses_email_and_django_password_hashing` |
| Password validation | `AuthenticationSecurityTests.test_password_change_rejects_current_and_short_passwords` |
| Password reset expiration | `AuthenticationSecurityTests.test_password_reset_token_expires` |
| Sessions invalidated after password change | `AuthenticationSecurityTests.test_password_change_invalidates_all_sessions` |
| Sessions invalidated after deactivation | `SessionSecurityTests.test_deactivation_revokes_all_sessions` |
| MFA-required OWNER login | `MFASecurityTests.test_owner_login_requires_password_and_valid_mfa` |
| MFA-required CASHIER login | `MFASecurityTests.test_cashier_login_requires_password_and_valid_mfa_when_policy_enabled` |
| Invalid TOTP | `MFASecurityTests.test_invalid_totp_is_rejected` |
| Used recovery code rejection | `MFASecurityTests.test_recovery_code_can_complete_mfa_login_only_once` |
| Recovery-code regeneration | `MFASecurityTests.test_recovery_codes_are_hashed_single_use_and_regeneration_invalidates_old_codes` |
| Login throttling | `LoginProtectionTests.test_five_failures_create_temporary_email_ip_lockout_and_safe_logs` |
| Temporary lockout expiration | `LoginProtectionTests.test_lockout_expires_instead_of_permanently_locking_account` |
| Enumeration-resistant messages | `AuthenticationSecurityTests.test_password_reset_does_not_enumerate_accounts`; `PublicBookingSecurityTests.test_status_lookup_requires_reference_and_token_without_enumeration` |
| Permissions for every role | `AuthorizationMatrixTests.test_direct_dashboard_urls_enforce_role_server_side`; role-specific matrix tests |
| Direct URL attempts | `AuthorizationMatrixTests.test_owner_only_business_and_security_surfaces` |
| Object-level authorization | `AuthorizationMatrixTests.test_scoped_queryset_blocks_changed_object_ids`; `PublicBookingSecurityTests.test_internal_querysets_enforce_management_and_assignment_scope` |
| Owner-sensitive reauthentication | `MFASecurityTests.test_owner_can_complete_reauthentication_then_change_sensitive_policy` |
| Public booking verification | `PublicBookingSecurityTests.test_successful_verification_confirms_and_issues_hashed_access_token` |
| Public booking token isolation | `PublicBookingSecurityTests.test_status_cancel_and_reschedule_tokens_are_bound_to_one_booking` |
| CSRF enforcement | `InputSecurityTests.test_activation_state_transition_requires_csrf_protected_post`; `InputSecurityTests.test_browser_form_actions_reject_missing_csrf_tokens` |
| Unsafe redirect rejection | `LoginProtectionTests.test_external_redirects_are_rejected_across_authentication_flows` |
| Upload validation | `UploadSecurityTests` |
| Live service image validation and safe names | `ServicesModuleTests.test_valid_image_uses_safe_name_and_invalid_image_is_rejected` |
| Service image replacement/deletion cleanup | `ServicesModuleTests.test_direct_model_image_validation_and_file_cleanup` |
| Service and StaffProfile role permissions | `ServicesModuleTests.test_catalog_read_permissions_and_inactive_service_scope`; `test_management_routes_are_owner_only` |
| Service/category constraints and role validation | `ServicesModuleTests.test_category_and_service_validation_and_constraints`; `test_staff_profile_accepts_only_staff_and_preserves_user_on_delete` |
| Audit logs exclude secrets | `SecurityEventTests`; Axes assertions in `LoginProtectionTests` |

## Required Integration Scenarios

| Scenario | Automated evidence |
|---|---|
| OWNER password and MFA login | `MFASecurityTests.test_owner_login_requires_password_and_valid_mfa` |
| CASHIER password and MFA login | `MFASecurityTests.test_cashier_login_requires_password_and_valid_mfa_when_policy_enabled` |
| STAFF login and restricted dashboard | `AuthorizationMatrixTests.test_staff_password_login_reaches_restricted_dashboard_only` |
| Deactivation while sessions are active | `SessionSecurityTests.test_deactivation_revokes_all_sessions` |
| Password reset while another session is active | `AuthenticationSecurityTests.test_password_reset_is_single_use_and_invalidates_sessions` |
| STAFF attempts owner reports | `AuthorizationMatrixTests.test_staff_password_login_reaches_restricted_dashboard_only` |
| CASHIER attempts account management | `AuthorizationMatrixTests.test_cashier_operational_permissions_and_limits` |
| Public booking-reference enumeration attempt | `PublicBookingSecurityTests.test_status_lookup_requires_reference_and_token_without_enumeration` |
| Expired or used verification token reuse | `AuthenticationSecurityTests.test_activation_sets_password_verifies_email_and_is_single_use`; `test_expired_activation_is_rejected` |
| Repeated failures followed by lockout | `LoginProtectionTests.test_five_failures_create_temporary_email_ip_lockout_and_safe_logs` |

## Required Command Evidence

Capture current output for:

```text
python manage.py makemigrations --check --dry-run
python manage.py migrate
python manage.py check
python manage.py check --deploy
python manage.py test
```

Do not suppress checks or convert warnings/errors into ignored results solely to produce a pass. `check --deploy` must run with the intended production environment, not development defaults.

## Known Test Gaps

- Service images are the current live upload surface; no other module accepts uploads.
- No POS, payment, discount, receipt, or financial total implementation exists.
- No appointment overlap, business-hours, service-duration, or concurrency tests exist.
- No full business workflow crosses booking approval, assignment, service status, POS, reports, and forecasting because those modules are incomplete.
- No immutable external audit sink or retention integration is tested.
- No production reverse proxy, TLS termination, SMTP delivery provider, shared cache, backup, or restore is exercised by Django tests.
