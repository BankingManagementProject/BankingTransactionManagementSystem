# Northstar Bank — merged requirements build

This merged package uses the independent services and separate persistent data volumes from the microservices edition, and incorporates the stale-Saga recovery capability from the original Spring Boot Saga project, reimplemented for the microservices orchestrator.

## Architecture
- Identity service: registration, login, JWT authentication and role issuance.
- Account service: account applications, employee verification, manager approval, account ownership and deposit approval workflows.
- Transaction service: transfer Saga orchestration, transaction history/events, admin-only failure simulations, staff recovery endpoint and scheduled stale-Saga recovery worker.
- Ledger service: internal-only balances and idempotent postings.
- RabbitMQ: event publication; this is not a complete event-driven saga coordinator.
- React/TypeScript frontend served by Nginx as the API routing layer.
- Separate SQLite database files in named Docker volumes; clean startup has no demo customers, accounts or transactions.

## Rules and roles
- Savings minimum balance: ₹1,000.
- Daily outgoing transfer limit: ₹25,000; date checks use India Standard Time.
- A process-local transfer lock serializes transfers when running one transaction-service replica. Do not scale that service horizontally without replacing this with a distributed/DB-level concurrency strategy.
- Customers can access only their own account and transaction records. Employees and managers have distinct approval permissions; admin can bootstrap/create staff and run controlled failure scenarios.
- Account application lifecycle: PENDING_REVIEW → VERIFIED → APPROVED.
- Deposit lifecycle: PENDING_APPROVAL until staff approval; rejection does not credit funds.
- Transfer outcomes: validation failures stop before debit; successful transfer requires confirmed debit and credit; failed credit triggers idempotent compensation; unresolved or ambiguous outcomes go to REQUIRES_REVIEW.

## Recovery behavior
The transaction service checks every 30 seconds for transfers stuck for more than 120 seconds in debit-in-flight states. It checks the ledger for the deterministic destination-credit reference before compensation. If a credit exists but the terminal Saga status is uncertain, it escalates to REQUIRES_REVIEW rather than risking a duplicate refund. If no credit exists, it issues a uniquely referenced compensation posting; only after the ledger confirms that posting does it mark COMPENSATED. Configuration: SAGA_RECOVERY_STALE_SECONDS and SAGA_RECOVERY_INTERVAL_SECONDS.

## Honest limitations
This is an educational simulator, not a real banking system. It still needs production-grade double-entry accounting, transactional outbox and durable event consumption, distributed locking/atomic daily-limit reservations for multiple replicas, reconciliation and alerting, robust retry/backoff policies, security review, MFA/OTP and session revocation, rate limiting, KYC/compliance controls, and automated end-to-end failure testing. SQLite is used for easy local startup. Do not use real customer or financial data.

## Run
1. Copy `.env.example` to `.env` and replace every sample secret.
2. Start Docker Desktop.
3. Run `docker compose up --build -d` from `northstar-rebuild/`.
4. Open http://localhost:5173.

Docker build and full browser workflows must be verified on your machine; archive integrity and Python syntax checks do not prove the entire stack runs correctly.


## Latest enhancement pass
Added a notification service for SMTP email verification and transfer OTP, branch assignment/scoping, optional Google login, a fixed-deposit demo workflow and a loan application/approval demo. SMTP and Google OAuth require user-provided credentials in `.env`. Fixed deposits/loans are educational workflows, not production financial products. End-to-end Docker and browser tests remain unverified in this build environment.
