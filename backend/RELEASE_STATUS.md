# Current release — 29 October 2026

This section supersedes all historical setup and launch instructions below.

## Implemented

- Public website links to the deployed member portal and public schedule.
- Password login, email verification/reset, and owner email-code second factor.
- SMS is hard-disabled. No paid upgrades or merchant requests are authorized.
- Owner management, audit trail, player review, coach self-registration and owner-controlled squad access.
- Role-specific dashboards, one-time welcome, private feedback/attendance, application decisions.
- Upcoming/history training pagination; private/shared calendars; explicitly published public events; ICS exports.
- In-app notifications, review decisions, action links, personal read state and revised-message unread state.
- Server-priced registration and dues integration, private receipts and owner-recorded external refunds. Manual transfer reports require an exact received amount, confirmed receiving-bank reference, owner verification and duplicate-reference checks. Receipts explicitly identify owner verification. Reports preserve the receiving instructions and terms accepted.
- Coach-only and owner accounts are not charged player registration fees. Approved dual-role players retain dues access.

## Not operational or not verified

- Automatic payment collection and refunds: disabled. No approved merchant credentials or real payment test. No merchant-access request will be made. The owner selected manual transfer verification on 26 October.
- New player submission requires verified registration payment. The owner can now verify a reported bank transfer to unlock submission, without merchant checkout. Receiving account details and terms must first be entered in /owner/transfers/settings/. No invented account details or approval bypass.
- Coach registration does not require player fees but still requires email verification and owner approval.
- Full phone/tablet visual QA and a new-player production email/application/approval round trip remain unverified; automated tests do not replace them.
- Recurring durable backups and scheduled cleanup remain outstanding on current hosting. Historical recovery checkpoints are not recurring backups.
- Notifications are in-app, not automatic outbound email/SMS/push reminders.

## Handover status — 26 October 2026

The live receiving-account configuration has been saved and enabled by the owner. A read-only check confirmed that the account number has ten digits and the name/terms are present; bank ownership was not independently verified. No real transfer was made or approved during testing.
The live desktop login page was visually inspected. Full phone/tablet and authenticated workflow visual checks remain outstanding.
The owner reviews reported transfers at /owner/transfers/. Only confirm after checking the actual receiving account. Approval produces a receipt and allocates dues; registration payment then unlocks application submission, followed by a separate admission decision.
Manual transfer orders cannot also be opened in automatic checkout. Completed orders cannot be charged again through that entry point.

## Validation

128 automated tests passed, including complete player/coach HTTP onboarding journeys, owner email-code verification, owner-only cleanup, CSRF protection, and preservation of active sessions and financial records. Django reported no pending model migrations. No live transfer or payment has been performed. Neon reports an empty snapshot schedule; recurring backups remain outstanding.

## Usability corrections — 29 October 2026

- Secondary buttons inside light panels now use dark green text and clear selected/hover states. This fixes unreadable training-history, notification-filter and payment links without changing the dark header/hero buttons.
- Email verification directs members to their dashboard rather than incorrectly claiming every account can submit a player application immediately.
- Verified applicants without a confirmed registration payment see the payment/status step and an explicit instruction not to pay twice. Paid applicants see the application step. Coach onboarding remains fee-free.
- Responsive grids allow columns to shrink, long text wraps inside cards and small-phone panel padding is reduced. Full device visual verification remains outstanding.

## Release verification — 29 October 2026

- Added disposable-database HTTP journeys with CSRF enabled and a local email outbox. Player signup, email verification, reported registration transfer, owner email-code login, exact-amount bank confirmation, application approval and Acceptance Letter all pass together. Three months of dues produce three private monthly receipts; another member cannot access them.
- Coach signup, email verification, profile submission and owner squad approval pass without creating a payment order. Coach access does not grant owner access.
- All 128 tests passed. No pending model migrations. Provider-error messages in this test run are expected mocked cases, not production delivery attempts.
- Live desktop registration was visually inspected with the updated fee explanation. Phone/tablet visual checks remain unverified: the Chromium download failed, and the available cloud browser has no viewport resizing control.
- Neon again rejected scheduled snapshots with “backup schedule creation is not enabled for this project”. No paid plan or resource was enabled. The historical snapshot expiry was 28 October; do not describe it as a fresh backup. Recurring backups remain outstanding.
- No real emails, bank transfers, admissions, or financial records were created by these tests. A new-player production email and bank-payment round trip remains unverified.
- The 27 October completed training record and the 29 October 3:30 p.m. WAT training announcement are published. Public static news and portal announcements must be maintained separately.
- Registration is ₦5,000 once; monthly training dues are ₦3,000 after admission. Approved applicants with verified registration payment can print an Acceptance Letter. Coach-only accounts remain exempt from player fees.

## Operations guide update — 26 October 2026

Owner controls now link to /owner/operations/, a compact guide for player and coach onboarding, transfer verification, dues, refunds, announcements and private schedules. An explicit, CSRF-protected owner action removes only expired sessions and rate counters and writes an audit entry. GET requests never clean records. This is manual maintenance, not a scheduled job or backup.

## Owner use

Sign in at https://warkfin-academy-portal.onrender.com/ using the owner account.
Use Owner controls for player/coach reviews, squads, training, announcements, calendar events and audit records.
For public events, select Published and Public without a squad or private recipient.
Private recipient events must never be marked public. Individual player records remain private.
Refund recording acknowledges a separately completed provider transaction; it never transfers money.

## Historical record (not current operating instructions)

# Initial registration release — 23 October 2026

This current status supersedes the historical opening instructions below.

- Owner password + email-code verification succeeded on 22 October at 14:12 UTC.
- Render deploy `dep-dbd1lrl9fdbs73a7hcag` is live with `PORTAL_ENABLED=1`
  and `OWNER_SETUP_ENABLED=0`; activation and startup invitations remain disabled.
- The public `/accounts/register/` page was verified in the browser on 23 October:
  email, password, confirmation and Create account are visible after host wake-up.
- Initial player onboarding is open. A complete new-player production submission,
  verification-email round trip and owner approval have not yet been checked.
- The existing code passed 61 automated tests before deployment. No application
  code changed during this status verification. Full mobile visual QA remains open.
- SMS delivery is unconfirmed. Use the verified email-code option for owner login.
- Fresh snapshot creation hit the Neon snapshot limit. A separate no-compute
  recovery branch `br-green-bread-b9dhol4h` was created from the live branch at
  22 October 14:16 UTC. It is a one-time checkpoint, not scheduled backup.
- Scheduled backups and routine cleanup scheduling remain outstanding. This is
  initial use, not a declaration that every production-readiness item is complete.
- Public academy navigation integration and the backend PR merge remain pending.

Players create an account, verify their email, submit their application and await
owner review. Do not automatically assign coach privileges, squads or directory
identities. Individual attendance and coaching feedback stay private.

## Historical release notes

# Owner preparation release — 21 October 2026

## Verified

- Owner email delivery and private password activation completed.
- 28 directory players, two squads and one active verified owner retained.
- 50 automated Django tests pass, covering role isolation, registration validation,
  owner enrolment, authenticator replay prevention, recovery-code single use,
  CSRF, session expiry, device revocation and the closed public launch gate.
- MFA uses django-otp 1.7.5. QR images are generated locally; no external QR API.
- The owner must enter their password to enrol and confirm a six-digit code.
- Recovery codes are high-entropy values stored only as SHA-256 digests.
- The full MFA table definitions generated by Django's PostgreSQL schema editor
  were executed successfully against the restored recovery copy.

## Hosting and database identity

Render service: `srv-dbbr1j3l550s73fv20eg`.
Live application database: Neon project `rough-bread-84107715`, branch
`br-steep-cherry-b9oyhj1y`, named `production-live`, database `academy`.
Always specify this branch ID explicitly. The Neon default branch is currently
`br-round-star-b9vrv864`, the recovery check copy, NOT the application database.

During the recovery rehearsal, Neon snapshot finalization reassigned the original
connection endpoint and default branch to the restored copy. The Render database
variables were corrected to target the original branch's replacement endpoint.
No player or owner records were removed. A read-only count check confirmed the
original data; all portal data routes remained closed throughout the rehearsal.

## Backups and recovery

Snapshot `snap-twilight-salad-b9noilur` was created before MFA deployment and
restored successfully. It expires 28 October 2026 at 20:00 UTC. The isolated
recovery copy retains 28 players, two squads and one active verified owner.
It has also been used to validate MFA table definitions; do not use it as live data.
Neon's configured continuous history is six hours (21600 seconds).
Automatic snapshot schedule creation was attempted and rejected by Neon:
"backup schedule creation is not enabled for this project". No paid upgrade was
made. A durable scheduled backup arrangement is still outstanding.

To make a manual snapshot, use the explicit live branch ID above. For another
recovery rehearsal, restore with `finalize: false`, then verify endpoint ownership
before any finalization. Never replace or finalize over the live branch merely
to test a backup. After a real recovery, check migration state and counts before
changing application connection variables. Never put database URLs, password
hashes, MFA keys or backup contents into public GitHub files or CI artifacts.

## Opening sequence

1. Deploy with `OWNER_SETUP_ENABLED=1`, `PORTAL_ENABLED=0`, and both
   `OWNER_ACTIVATION_ENABLED=0` and `OWNER_INVITE_ON_START=0`.
2. Owner signs in at `/accounts/login/`, enrols their private authenticator at
   `/accounts/security/`, and saves the recovery codes offline.
3. Confirm a confirmed owner TOTP device exists without reading its secret.
4. Complete real browser checks. A local Playwright script was prepared but
   Chromium installation failed; visual/browser checks are NOT yet passed.
5. Resolve ongoing backup scheduling, then set `PORTAL_ENABLED=1` and verify
   registration, verification email and role-specific dashboards in production.
6. Only then publish portal links on the public academy website.

Owner preparation mode allows the login page and authenticated owner routes,
but blocks registration and other users. MFA middleware still protects every
owner data route, including admin. Activation is not public registration.

## Operations

Keep account invitations and bootstrap activation disabled. Use the owner admin
for verified coaching assignments and training announcements. Do not assume the
28 listed players have accounts or assign squads without confirmation.
Run `python manage.py cleanup_portal` periodically to remove expired rate buckets
and sessions; scheduling this remains an operations task on the free host.
MFA loss requires a saved recovery code plus the password. There is intentionally
no email-only MFA bypass. Review recovery procedures privately if all codes and
the authenticator are lost.


## SMS revision — 22 October 2026

At the owner's request, deployment uses OWNER_MFA_METHOD=sms. The confirmed
phone is set privately in OWNER_SMS_PHONE on Render, never accepted from a login
form. The authenticator and QR setup are bypassed in SMS mode without bypassing
second-factor verification. Existing TOTP records are retained, not deleted.
SMS codes expire in five minutes, are browser-bound, keyed-hashed, single-use,
and limited to five verification attempts. Sends have a 60-second cooldown and
10-per-hour limit, including provider failures. Brevo accepts messages via its
transactional SMS API. Acceptance does not prove delivery. Sender Warkfin must
be approved for Nigeria and sufficient SMS credits must be available. No paid
credits are purchased automatically. Startup checks read account credit status
without sending messages or exposing personal account information.

56 automated tests pass, including six SMS security regression tests. Public
registration remains closed until actual SMS delivery, owner access and the
remaining release checks are completed. The original authenticator enrolment
step above is superseded by password + SMS verification. SMS recovery is not
implemented as an email bypass; lost-phone recovery requires private support.

## Email alternative — 22 October 2026

Owner verification now offers email or SMS after password authentication. Email
codes are sent only to the already-verified account email; the form cannot change
the recipient. Both methods share cooldowns, an hourly quota and one pending
challenge so switching channels invalidates the earlier code. Codes include the
channel and contact identity in the keyed digest. A change of account email
invalidates existing verified sessions. This explicitly requested email option
supersedes the earlier SMS-only recovery policy; it is not a password bypass.
61 automated tests pass, including destination tampering, email delivery failure,
single-use email verification and cross-channel invalidation. Startup diagnostics
read recent ownerLogin delivery events without logging message content or secrets.
SMS acceptance was recorded at 00:29 UTC after the owner's Brevo permission change;
actual phone delivery is not implied. Public launch remains closed.
