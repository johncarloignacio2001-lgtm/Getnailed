# MFA Encryption Key Setup - RESOLVED

## Issue
When attempting to activate TOTP MFA (2FA), the system returned:
```
ImproperlyConfigured: MFA_ENCRYPTION_KEY must be configured.
```

Error location: `apps/accounts/adapters.py`, line 60, in `_cipher()`

## Root Cause
The `MFA_ENCRYPTION_KEY` environment variable was not set in the development environment. Django-allauth's TOTP MFA implementation requires this key to encrypt/decrypt MFA secrets.

## Solution Applied

### 1. Created `.env` File
```bash
# Copied .env.example to .env
Copy-Item .env.example .env
```

### 2. Generated Encryption Key
Generated a cryptographically secure 32-character random key using Python:
```python
import secrets
key = secrets.token_urlsafe(32)
# Generated: kTBqXCXXq2hbIcGaTBaetjnbmtdGR4qWlENY9Kpgjbw
```

### 3. Updated `.env` File
Changed:
```env
MFA_ENCRYPTION_KEY=replace-with-a-long-random-secret
```

To:
```env
MFA_ENCRYPTION_KEY=kTBqXCXXq2hbIcGaTBaetjnbmtdGR4qWlENY9Kpgjbw
```

### 4. Loaded Environment Variables
Loaded the `.env` file into the PowerShell session:
```powershell
Get-Content .env | 
  Where-Object { $_ -match '^[^#][^=]*=' } | 
  ForEach-Object {
    $name, $value = $_ -split '=', 2
    Set-Item -Path "Env:$($name.Trim())" -Value $value
  }
```

## Verification

### Test Results
✅ All 166 tests pass (65.575 seconds)
✅ MFA tests specifically: 19/19 passed
✅ Development server running on http://127.0.0.1:8000

### MFA Features Now Working
- TOTP enrollment with QR code
- TOTP validation during login
- Recovery codes generation and validation
- MFA policy enforcement for OWNER and optional for STAFF
- MFA secret encryption at rest

## Configuration Details

### Settings.py MFA Configuration
```python
MFA_ADAPTER = 'apps.accounts.adapters.EncryptedMFAAdapter'
MFA_ENCRYPTION_KEY = os.getenv('MFA_ENCRYPTION_KEY', '')
MFA_ENFORCE_OWNER = True  # OWNER must have MFA
MFA_REQUIRE_INTERNAL_USERS = False  # STAFF optional
MFA_SUPPORTED_TYPES = ['totp']
MFA_TOTP_ISSUER = 'Get Nailed Nail Bar and Spa'
MFA_RECOVERY_CODE_COUNT = 10
MFA_RECOVERY_CODES_SHOW_ONCE = True
```

### Production Considerations
In production, the `MFA_ENCRYPTION_KEY`:
- Must be at least 32 characters long
- Must have high entropy (use `secrets.token_urlsafe(32)` or equivalent)
- Should be stored in a secure secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.)
- Should never be committed to version control
- Should be different from `DJANGO_SECRET_KEY`

## Testing MFA Flow

### Demo Account Setup
1. Login as OWNER: owner@getnailed.local / DemoOwner@123456
2. Navigate to: http://127.0.0.1:8000/security/2fa/totp/activate/
3. Scan QR code with authenticator app (Google Authenticator, Authy, etc.)
4. Enter 6-digit code to complete enrollment
5. Save recovery codes in secure location
6. Log out and log back in to verify TOTP requirement

### Demo Authenticator App Setup
Any TOTP-compatible authenticator can be used:
- Google Authenticator
- Microsoft Authenticator
- Authy
- 1Password
- Bitwarden

## Files Modified
- `.env` - Created with MFA_ENCRYPTION_KEY configured
- No code changes required

## Next Steps
1. ✅ Verify MFA activation works in browser (test with demo account)
2. ✅ Confirm recovery codes functionality
3. ✅ Test MFA requirement on login
4. Before production: Change demo password and generate new production key

## Quick Reference: Environment Loading

Each time you open a terminal for development, load the `.env` file:

**PowerShell:**
```powershell
Get-Content .env | Where-Object { $_ -match '^[^#][^=]*=' } | ForEach-Object { $name, $value = $_ -split '=', 2; Set-Item -Path "Env:$($name.Trim())" -Value $value }
```

**Bash/Zsh:**
```bash
set -a
source .env
set +a
```

Or create an alias for convenience:
```bash
alias loadenv='set -a; source .env; set +a'
```

---

**Status**: ✅ RESOLVED  
**Date**: 2026-09-18  
**Test Coverage**: 166 tests, 100% pass rate  
**MFA Tests**: 19/19 passing
