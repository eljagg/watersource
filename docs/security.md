# Security controls (ToR §9 → implementation)

| Requirement | Where |
|---|---|
| Application-managed accounts, no SSO/AD | `accounts.User`, no external auth backends |
| Password length/complexity, rotation, history, lockout, reset | `AUTH_PASSWORD_VALIDATORS` (12+ chars, 3 classes, no reuse of last 10), `PasswordPolicyMiddleware` (90-day staff rotation), django-axes (5 failures → 15-min lock), Django reset flow with single-use tokens |
| Email verification for clients; staff created by admin | `accounts.views.register` / `EmailToken`; admin |
| MFA for approver/administrator | django-otp TOTP, `MFAEnforcementMiddleware`, `MFA_REQUIRED_GROUPS` |
| Session timeout | 20-min idle (`SessionPolicyMiddleware`), 8-h absolute, secure/HttpOnly/SameSite cookies |
| SQLi | ORM only; ruff rule S608 flags string-built SQL; the one raw SQL is the BI migration |
| XSS | template auto-escape; CSP with per-request nonces, no inline scripts |
| CSRF | Django CSRF on every state change incl. htmx (`X-CSRFToken`) |
| Clickjacking | `X-Frame-Options: DENY`, `frame-ancestors 'none'` |
| Upload validation | size cap, extension vs libmagic type, stored outside web root, served only via authenticated download view |
| Malware scanning | ClamAV INSTREAM before a file is linked (`core.uploads.clamav_scan`); infected files are deleted and logged |
| RBAC | roles as groups; stage-bound approver groups; `PublishedQuerySet.visible_to()` for data; DB roles for BI/export |
| Audit logging | `core.AuditLog` (append-only) for every workflow action, upload, download, auth event, correction, export |
| Encryption in transit | TLS 1.2+ at nginx (HSTS, preload); internal services on the Docker network only |
| Encryption at rest | LUKS on the app-vm data disk; AES-256 pgBackRest repository; argon2id password hashes; API keys stored hashed |
| Rate limiting | axes on login; DRF throttles (anon 60/min, user 600/min, key 1200/min); nginx `limit_req` on `/accounts/` |
| Dependency and image hygiene | pip-audit, bandit, ruff (S rules), Trivy in CI |
| VAPT | OWASP ZAP authenticated scans per role from Stage 6; independent VAPT before UAT exit; Critical/High fixed before go-live |

Target standard: OWASP ASVS 5.0 Level 2 (the recommended level for systems handling personal data).
