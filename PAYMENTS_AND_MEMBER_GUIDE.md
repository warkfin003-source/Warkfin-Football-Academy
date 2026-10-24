# Academy fees and member workspace

Registration is NGN 5,000; dues are NGN 3,000 per calendar month. Account creation and email verification precede payment. Application submission and owner approval require a verified registration payment. Existing approved memberships are preserved; they are not silently marked paid or charged retrospectively.

## What is available
- Private payment history, PAID status, receipt pages with Print / Save as PDF.
- Dues periods of 1, 3, 6, 9 or 12 consecutive calendar months, no automatic recurring debit. Each paid month has its own slip; it references the parent payment and is not an additional charge.
- Separate acceptance slip after owner approval and verified registration payment.
- Calendar with month selection; training and owner-published courses/appointments; downloadable ICS with a one-hour reminder. Calendar app settings control notifications. Downloads do not automatically sync changes.
- In-portal news/notifications and personal read markers. No background SMS/push/email notification service is claimed.
- Coach profiles for Smith, Messi and Oracle, and appointment requests from approved players. The owner reviews these in admin. Confirmation creates a private one-hour calendar event; publish the agreed location on that event. Changing the request to declined/pending unpublishes it.
- Coach profiles create no user accounts and grant no access. Obtain each coach's email, create/verify their account, then explicitly assign squads. Do not grant owner/superuser rights to coaches.

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

A callback requires a valid PalmPay signature and matching App ID. The server then independently queries the provider. Only status 2 with the expected order ID, amount and NGN currency produces PAID and receipts. Browser redirects and user-supplied amounts never count as payment proof. Pending orders are reused; check their status before retrying. Refund automation is not implemented: process any agreed refund through the provider and reconcile records before issuing revised receipts. Do not enable collection until this operational process is agreed.

## Source references
- https://docs-daily.palmpay.com/en/pay-ins-palmpay-checkout-create-order.html
- https://docs-daily.palmpay.com/en/pay-ins-palmpay-checkout-query-order-result.html
- https://docs-daily.palmpay.com/en/basics-of-access-signature-method.html
- https://docs-daily.palmpay.com/en/pay-ins-common-apis-payment-result-notify.html
- https://docs-daily.palmpay.com/en/basics-of-access-data-dictionary.html

## Owner workflow
Admin contains coach profiles, academy events, appointment requests, payment orders and dues months. Financial records are read-only. Publish events intentionally; a recipient makes an event private to that account. Player receipts and notifications never expose other players' payment or attendance records.
