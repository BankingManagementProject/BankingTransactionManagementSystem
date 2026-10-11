# Mandatory requirements coverage

| Requirement | Current implementation | Boundary / caveat |
|---|---|---|
| JWT authentication | Identity service issues signed, expiring JWTs; passwords are scrypt-hashed | No MFA/OTP, refresh rotation, password reset, or revocation |
| Role authorization | Customer, Employee, Manager, Admin checks are enforced in backend routes | Review every new route before adding it |
| Account application | Customer applies; employee verifies; manager approves | Educational workflow; no KYC/regulatory integrations |
| Deposit approval | Pending request is not credited until staff approval | Must be tested end-to-end with Docker |
| Savings minimum | Transfer validation keeps configured minimum balance (₹1,000 default) | Concurrent invariants rely on one transaction-service replica |
| Daily outgoing limit | ₹25,000 default; only debit-relevant outcomes count; date boundary uses IST | Do not horizontally scale transaction service without shared locking/reservations |
| Saga transfer | Persisted stage events; validation stop; debit, credit, compensation; review queue and staff recovery | Synchronous orchestration; no transactional outbox or automated crash-recovery worker |
| Ledger idempotency | Unique posting references; identical retries are idempotent; conflicting reuse rejected | Not a complete double-entry accounting ledger; no external reconciliation |
| Clean startup | Empty named volumes create no demo users/accounts/transactions | Bootstrap first admin intentionally |
| Docker Compose | Frontend, four services, RabbitMQ, and named persistent volumes | Full Docker/browser acceptance test still required on a machine with Docker |

This is a coursework simulator, not a production banking platform. Do not use real customer data or money.


## Added feature coverage (this update)
- Staff branch assignment and backend branch scoping for staff account/application/deposit/loan queues; Admin remains cross-branch.
- Customer selects a branch for each account application.
- Notification microservice sends registration email verification and transfer OTPs through configured SMTP. Transfer endpoint validates and consumes a one-time OTP.
- Optional Google Identity Services login requires `GOOGLE_CLIENT_ID` configuration.
- Fixed deposit demo: debit/lock principal, 6.5% simple interest estimate and maturity-only manual payout.
- Loan demo: application, branch-scoped review, approval/disbursement or rejection. Repayment schedules and production lending controls are not included.
- Timeline polling no longer refetches/rewrites the selected timeline on every refresh interval, fixing the visible blinking issue.
