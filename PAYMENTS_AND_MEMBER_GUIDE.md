# Academy fees and member workspace

Registration is NGN 5,000; dues are NGN 3,000 per calendar month. Account creation and email verification precede payment. Application submission and owner approval require a verified registration payment. Existing approved memberships are preserved; they are not silently marked paid or charged retrospectively.

## What is available
- Private payment history, PAID status, receipt pages with Print / Save as PDF.
- Dues periods of 1, 3, 6, 9 or 12 consecutive calendar months, no automatic recurring debit. Each paid month has its own slip; it references the parent payment and is not an additional charge.
- Separate acceptance slip after owner approval and verified registration payment.
- Calendar with month selection; training and owner-published courses/appointments; downloadable ICS with a one-hour reminder. Calendar app settings control notifications. Downloads do not automatically sync changes.
- In-portal news/notifications and personal read markers. No background SMS/push/email notification service is claimed.
- Coach profiles for Smith, Messi and Oracle, and appointment requests from approved players. The owner reviews these in admin. Confirmation creates a private one-hour calendar event; publish the agreed location on that event. Changing the request to declined/pending unpublishes it.
- Coaches register at `/accounts/register/?role=coach`, verify email and submit `/coach/register/`. The owner reviews profiles and assigns squads. Approved coaches can edit private profile details at `/coach/profile/edit/`; edits never change their permissions. Public coach profiles remain owner-managed.

## PalmPay activation — collection is OFF by default
The business account alone is insufficient for API checkout. Obtain approved PalmPay Checkout merchant access. Never paste private keys in chat or commit them.

1. Confirm merchant identity and enable the supported collection methods (bank transfer, wallet/card as approved).
2. In a separate test environment, configure `PALMPAY_APP_ID`, `PALMPAY_PRIVATE_KEY`, `PALMPAY_PUBLIC_KEY` (PalmPay's verification public key), and `PALMPAY_BASE_URL=https://open-gw-sandbox.palmpay-inc.com`.
3. Set `PALMPAY_CHECKOUT_HOSTS` to the exact checkout hosts supplied by PalmPay. Do not use arbitrary wildcard hosts.
4. Agree and publish written fee coverage, cancellation/refund terms; place that approved text in `PAYMENT_TERMS`.
5. Confirm outgoing request signing, provider callbacks, amount/currency/reference matching, failure and retry paths, expiry, one real sandbox payment, duplicate callback handling, and monthly allocation. Unit tests alone are not merchant certification.
6. Configure live approved credentials on Render with `PALMPAY_BASE_URL=https://open-gw-prod.palmpay-inc.com`. Only after the preceding checks, set `PALMPAY_ENABLED=1`. Sandbox collections are blocked when Django DEBUG is false.
7. Callback: `/payments/palmpay/notify/`; browser return: `/payments/`. Both use the configured HTTPS `PORTAL_ORIGIN`.
8. Perform a controlled real collection and verify settlement in the merchant account before public rollout.

A callback requires a valid PalmPay signature and matching App ID. The server then independently queries the provider. Only status 2 with the expected order ID, amount and NGN currency produces PAID and receipts. Browser redirects and user-supplied amounts never count as payment proof. Pending orders are reused; check their status before retrying. Refund automation is not implemented. The owner can record processing or a completed external refund at `/owner/refunds/<id>/`. Completion requires the provider refund reference and an explicit confirmation that the full registration payment was returned. The action does not move money. Completed records are locked; players see the separate owner-recorded refund status on their original receipt. Do not enable collection until the provider workflow is verified.

## Source references
- https://docs-daily.palmpay.com/en/pay-ins-palmpay-checkout-create-order.html
- https://docs-daily.palmpay.com/en/pay-ins-palmpay-checkout-query-order-result.html
- https://docs-daily.palmpay.com/en/basics-of-access-signature-method.html
- https://docs-daily.palmpay.com/en/pay-ins-common-apis-payment-result-notify.html
- https://docs-daily.palmpay.com/en/basics-of-access-data-dictionary.html

## Owner workflow
Admin contains coach profiles, academy events, appointment requests, payment orders and dues months. Financial records are read-only. Publish events intentionally; a recipient makes an event private to that account. Player receipts and notifications never expose other players' payment or attendance records.

## Owner workspace and record lifecycle
The owner dashboard at `/owner/` includes live counts, review queues, management shortcuts, gross recorded collections and outstanding refund obligations. `/owner/setup/` reports configuration presence without exposing keys; it is not a provider health check.

Players and public coaches support activate/archive actions. Announcements support publish/unpublish and individual deletion through Django's confirmation page. Financial records and audit logs cannot be deleted. Manage account activation using the user record; keep the owner account active. Squad coach assignments control access.

## Approved fee coverage
Registration (NGN 5,000 once): application processing, player profile and registration records, and onboarding after approval. Monthly dues (NGN 3,000): scheduled training, coaching costs, shared equipment maintenance and routine academy operations. Declined applications receive a registration refund. Personal kits, transport and competition charges are explained separately when applicable. Other cancellation terms still need to be settled before checkout activation.

## Email-only verification
SMS delivery and startup provider checks are disabled. The owner receives login codes at the verified account email. No SMS credits or paid upgrade is needed. Provider email sending quotas still apply; no paid service is enabled by this change. Existing SMS challenges cannot be used when SMS is disabled.
