# Backend code guide

The public academy website remains on GitHub Pages. This Django project provides the separate private member portal on Render, backed by Neon PostgreSQL.

## Where to make changes

| File or directory | Responsibility |
| --- | --- |
| `config/settings.py` | Environment settings, database choice, launch switches, email and cookie security |
| `config/migration_settings.py` | Direct PostgreSQL endpoint for migrations |
| `config/urls.py` | Routes connected to views |
| `academy/models.py` | Database entities and uniqueness constraints |
| `academy/migrations/` | Ordered schema history; add migrations rather than rewriting an applied migration |
| `academy/forms.py` | Editable fields and server-side validation |
| `academy/views.py` | Role checks, filtered queries and transactional workflows |
| `academy/middleware.py` | Closed-launch routing, request limits and cache/security headers |
| `academy/owner_activation.py` | Private first-owner password activation and token validation |
| `academy/email_backend.py` | Brevo HTTPS email adapter |
| `academy/admin.py` | Owner-only administration and audit logging |
| `academy/management/commands/` | Directory seeding, cleanup and controlled owner setup |
| `templates/` | Escaped HTML and account email templates; Django comments do not reach the browser |
| `static/academy/forms.js` | Conditional fields for student and graduate applications |
| `static/academy/portal.css` | Brand colours, raised panels, forms, mobile layout and focus styling |
| `academy/tests.py`, `academy/test_*.py` | Workflow, privacy, transport and activation regression tests |

## Important boundaries

- An account is not automatically an approved player.
- A public player directory entry is not an account and is not automatically assigned to a squad.
- Only the owner approves applications and matches existing directory records.
- Coaches see their assigned squads. Players see only their own attendance, availability and shared feedback.
- Availability describes intent; attendance records what actually happened.
- Media publication permission remains optional.
- Form field allowlists and server-side authorization are essential. Template conditions and JavaScript are not security controls.
- Audit events contain record identifiers, not copied private details or credentials.

## Staging and activation

Owner login email: `warkfin003@gmail.com`.

Render portal: https://warkfin-academy-portal.onrender.com/

`PORTAL_ENABLED=0` keeps sign-in, registration and private records closed. `OWNER_ACTIVATION_ENABLED` defaults to `0`. Once a verified email sender is configured, activation can be enabled separately while the rest of the portal stays closed. `invite_owner` emails the private link; it does not print it or set a shared password. Do not run it until email delivery is configured and sending is intended.

The pilot still requires actual email delivery testing, owner activation, owner MFA, a backup/restore check and browser testing before opening to players. These comments describe implemented behavior; they do not imply those launch checks have been completed.

## Change checklist

1. Change the responsible source file rather than generated `staticfiles/` assets.
2. Keep passwords, provider keys and database URLs in hosting environment settings.
3. For schema changes, create and review a new migration.
4. For access or workflow changes, run `DJANGO_DEBUG=1 python manage.py test academy` in the configured virtual environment.
5. Run `python manage.py collectstatic --noinput` during deployment builds.
6. Confirm the intended Render deployment is live and verify its behavior before opening the portal.

Keep comments focused on purpose, privacy rules and non-obvious decisions. Update comments when behavior changes.
