# Warkfin Football Academy backend — first implementation

This is a separate Django member portal for the existing GitHub Pages academy website. It is executable source, not a deployed login service. No real private player information, credentials or databases are committed. The existing public website is unchanged by this branch.

## Implemented

- Email/password accounts, signed 24-hour email verification, password recovery and password changes.
- Adult application form with server-side student/graduate conditional validation; optional media publication consent.
- Owner review, correction/decline/approval, and verified linking to an existing directory record.
- Separate owner, assigned-coach, player and pending-applicant dashboards.
- Owner administration for squads, coach assignments, player assignments, sessions and member announcements.
- Private availability responses, actual attendance and shared/staff-only development feedback.
- Player editing of their own phone, emergency contact and publication preference. Approved identity and football assignments remain owner-managed.
- Database-backed login/account-action throttling, CSRF protection, password hashing, no-store private responses and production HTTPS settings.
- Audit events for portal mutations and owner model edits, plus Django's own administration log.
- Idempotent import of 28 public names/positions through Nedu. Import does not create accounts, assign passwords or infer actual squad membership.

## Architecture

The Python service serves both private dashboard HTML and its form endpoints on one origin. Browser sessions use HttpOnly cookies; private data is never passed to the GitHub Pages JavaScript. After staging is tested, public navigation can link to the portal URL. This design does not need permissive cross-origin cookies or public database keys.

Development uses SQLite; production requires PostgreSQL. Django owns authentication. Only active superusers may enter `/admin/`. A coach's `is_staff` flag does not grant owner access. Assign a verified coach to specific squads in owner administration. Removing the assignment removes access on the next request. Deactivate an account to block all login; deactivate a player record to remove player access while retaining history.

Existing players create and verify their own accounts, then apply. The owner privately confirms identity and selects the matching unclaimed directory record during approval. No name-only account claiming is permitted. Automated invitation email workflows are not yet implemented.

## Local setup

Requires Python 3.12. Run from `backend/`:

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DJANGO_DEBUG=1
python manage.py migrate
python manage.py seed_directory
python manage.py bootstrap_owner --email YOUR_OWNER_EMAIL
python manage.py runserver 127.0.0.1:8000
```

On Windows PowerShell, activate with `.\.venv\Scripts\Activate.ps1` and set `$env:DJANGO_DEBUG="1"` instead of the two shell-specific lines above. Use the same Python commands afterward. Owner setup asks for a password privately; never put it in a command, source file or chat. Local verification/recovery emails print to the local development console. Do not share console output containing account links.

`.env.example` documents production variables; the app deliberately does not auto-load `.env` files. Set values in the host's secrets/environment settings. Production startup refuses missing secret keys, PostgreSQL configuration, HTTPS portal origin or email service configuration.

## Validation

```sh
DJANGO_DEBUG=1 python manage.py test academy
DJANGO_DEBUG=1 python manage.py makemigrations --check --dry-run
DJANGO_DEBUG=1 python manage.py check
DJANGO_DEBUG=1 python manage.py collectstatic --noinput
```

Tests cover account isolation, coach scoping and revocation, email verification, CSRF, approval/number allocation, existing-player linking, conditional application fields, attendance restrictions, profile spoofing, password-reset delivery, throttling and safe repeated directory import. Local tests use SQLite; production PostgreSQL and real email delivery must also be tested in staging.

## Hosting setup and release gate

1. Select a Python/container host and PostgreSQL service under the owner's account; agree any costs before provisioning paid resources.
2. Configure the variables in `.env.example`, with a unique secret key and verified sender domain/account. Never commit secrets.
3. Set the exact portal domain in `DJANGO_ALLOWED_HOSTS` and `PORTAL_ORIGIN`. Keep the portal on HTTPS.
4. The trusted proxy must strip spoofed forwarding headers and set the real client `REMOTE_ADDR`. Do not simply trust arbitrary `X-Forwarded-For`. Enable `TRUST_HTTPS_PROXY=1` only if the host supplies a sanitized `X-Forwarded-Proto`. Add host-level IP rate limiting alongside the application throttle.
5. Run `python manage.py migrate`, `python manage.py collectstatic --noinput`, and `python manage.py check --deploy` with production environment variables.
6. Start `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2`. Do not use Django's development server in production. The Dockerfile provides the same startup; migration/static collection are explicit release steps.
7. Bootstrap the owner, import the directory, confirm squad assignments and add authorised coach accounts. Use real email verification for coaches; never set shared default passwords.
8. Add owner multifactor authentication before public launch; this first implementation currently provides password authentication only.
9. Test real verification/reset emails, mobile/desktop dashboard interactions, PostgreSQL concurrent approvals, staff revocation and every access boundary with separate test accounts.
10. Configure database backups and perform a restore into an isolated database. Schedule `python manage.py cleanup_portal` daily. Agree retention periods and update the privacy notice with the selected host and contact details.
11. Invite a small pilot group. After sign-off, add Login/Apply links to the public site and retire or clearly distinguish the earlier WhatsApp-only registration form.

Do not launch publicly until these checks pass. No production hosting, email sender, domain, real owner account, backup schedule or MFA has been configured by this code change.

## Remaining work from the full academy plan

- Owner MFA and automated invitations; reliable email notifications/outbox for approval changes.
- Public news publishing and synchronisation with GitHub Pages; current announcements are portal-only.
- Photo upload/storage validation, dated media administration and publication-consent workflow. Existing public media remains in the current website.
- Historical squad membership/transfers, richer development goals and privacy-preserving exports.
- Sponsorship/contact enquiry handling, player document/photo uploads and retention/deletion workflow.
- Production monitoring, staging browser QA, database backup/restore rehearsal and agreed operating costs.

Payments and public comparative attendance/statistics are outside this first release. Health details and minors' registrations need a separately designed restricted workflow; the current form rejects under-18 applicants.

## Main routes

| Route | Access |
| --- | --- |
| `/accounts/register/`, `/accounts/login/` | Public |
| `/accounts/password_reset/` | Public, throttled |
| `/application/` | Verified applicant |
| `/profile/` | Approved active player, own contact fields only |
| `/` | Signed-in role-specific dashboard |
| `/owner/applications/<id>/` | Owner |
| `/coach/players/<id>/` | Owner or assigned coach |
| `/coach/sessions/<id>/` | Owner or assigned coach |
| `/admin/` | Owner only |
| `/health/` | Public minimal liveness status |

No endpoint lists private player records publicly. A healthy liveness endpoint does not prove the database or email service is available.
