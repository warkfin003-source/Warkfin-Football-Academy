# Warkfin Academy — owner operating guide

## Live services
- Public website: https://warkfin003-source.github.io/Warkfin-Football-Academy/
- Sign up: https://warkfin-academy-portal.onrender.com/accounts/register/
- Sign in: https://warkfin-academy-portal.onrender.com/accounts/login/
- Owner email: warkfin003@gmail.com

## Approve an application
1. Sign in with your password and choose email for the owner verification code.
2. Open the application under Applications awaiting review.
3. Review the verified applicant and confirm their identity privately. For an existing player, select the matching unclaimed directory entry; never link an account by name alone.
4. Approve, request a correction or decline with an appropriate note. Assign the correct squad through Manage academy.
5. Players then use their own login to access their private dashboard.

## Manage training
Use Manage academy for squads, training sessions and published announcements. Keep venues unconfirmed until agreed. Coaches only access assigned squads. Availability is a player's intention, not proof of attendance. Record actual attendance after a session, and keep individual feedback private. Do not publish attendance rankings.

## Public website versus member portal
Public news/photos remain maintained in the GitHub Pages website. Portal announcements are separate records for approved members; they do not automatically publish to GitHub Pages. Public registration now links to the portal and no longer sends a completed application through WhatsApp. WhatsApp is a help channel.

## Verified release — 24 October 2026
- Backend PR #2 merged into main, preserving the public design and media.
- Public signup/login entry points added across 27 pages, including mobile navigation and footer.
- 61 automated Django tests pass. Owner email-code sign-in previously confirmed.
- Live signup page checked; a complete real-player application and approval trial remains to be completed by the actual participant and owner.
- No shared passwords, automatic player-account claiming or automatic coach permissions.

## Remaining operational limits
- SMS phone delivery is unconfirmed; use owner email verification.
- Scheduled backups are not configured. Neon rejected snapshot scheduling and the snapshot count limit prevented another snapshot. The separate recovery branch is only a one-time checkpoint, not a backup schedule.
- Routine cleanup scheduling remains outstanding. The existing cleanup_portal management command removes expired sessions/rate-limit buckets.
- Render currently deploys the existing backend feature branch with auto-deploy off. Backend code is now also in main; do not delete the deployed branch until Render's branch setting is changed deliberately.
- The free Render service may sleep and take a moment to wake up. No paid plan or SMS credits were purchased.
- Do not represent the project as fully production-hardened until these operational checks are resolved.

Never commit credentials, live database exports, application details or verification codes. See backend/RELEASE_STATUS.md for the explicit live Neon branch; the default Neon branch is not the live application database.
