# Northstar Bank — genuine microservices MVP

Educational banking simulator with independently implemented services, separate persistent data stores, an API gateway, and a persisted Saga workflow. It starts with no users, accounts, or transactions.

## Architecture

- `frontend`: React + TypeScript website served by Nginx; Nginx is the browser-facing API gateway.
- `identity-service`: customer registration with email verification, password login, optional Google Identity Services login, signed JWTs, staff creation and branch-bound role claims. Own database: `identity_data`.
- `account-service`: branch-aware account applications, employee verification, manager approval, deposit approval, fixed deposits and loan applications. Own database: `account_data`.
- `transaction-service`: transaction records, stage timeline, transfer validation and Saga orchestration. Own database: `transaction_data`.
- `ledger-service`: balance ownership and idempotent debit/credit/compensation postings. Own database: `ledger_data`.
- `notification-service`: SMTP email verification codes and one-time transfer authorization codes, with expiry and attempt limits. Own database: `notification_data`.
- `rabbitmq`: durable event broker; the Saga service publishes transaction stage events to `northstar.events`.

Services are separate deployable FastAPI applications, with distinct Dockerfiles and persistent data stores. Account and transaction services use private HTTP APIs to request ledger operations; they do not read one another's database files. The services share JWT verification configuration, but each independently verifies the token and applies role checks. The internal service API uses a separate shared secret.

## Start

1. Copy `.env.example` to `.env`.
2. Replace all sample values with unique secrets. Use a random JWT key at least 32 characters long and a bootstrap secret at least 24 characters long.
3. Start Docker Desktop.
4. From this folder run:

   ```powershell
   docker compose up --build -d
   ```

5. Open http://localhost:5173.
6. Select **Initial administrator setup**, use the bootstrap secret from `.env`, create the first admin, then sign in.
7. Create an employee and a branch manager under **Staff access**, assigning each a branch. Register customers using **New customer? Register**; they must verify their email before signing in. Configure SMTP before customer registration. Customers choose a branch for each application.

Useful commands:

```powershell
docker compose ps
docker compose logs -f identity-service
docker compose logs -f account-service
docker compose logs -f transaction-service
docker compose logs -f ledger-service
```

The web app is on port 5173. RabbitMQ management is on port 15672 using the username/password in `.env`. Database files are stored in five named volumes. `docker compose down` preserves data; `docker compose down -v` deletes all service data.

## Workflow

### Account opening

Customer submits a complete application with name from authenticated identity, 10-digit mobile, date of birth (18+), residential address, occupation, account type, initial deposit and purpose/notes -> `PENDING_REVIEW` -> Employee verifies -> `VERIFIED` -> Manager approves -> Account Service creates account metadata and asks Ledger Service to create the ledger account/opening credit -> `APPROVED`/active. A savings application requires an initial deposit of at least ₹1,000 in this demo. See `REQUIREMENTS_COVERAGE.md` for the acceptance checklist.

### Deposit

Customer submits a deposit -> `PENDING_APPROVAL`; no balance changes. Employee/manager approval asks Ledger Service to post an idempotent credit, then records `SUCCESS`. Rejection records `REJECTED` and does not credit the ledger. Deposits are simulated, not actual cash or payment-rail deposits.

### Transfer Saga

Transaction Service persists `PENDING`, then `VALIDATING`. If the destination is missing, history ends at `VALIDATION_FAILED`; no ledger posting occurs. If validation passes, it records `VALIDATED`, posts a uniquely referenced debit, records `DEBIT_CONFIRMED`, attempts destination credit, and then records `SUCCESS` or runs compensation. Compensation is a new idempotent credit to the source, recorded as `COMPENSATED` only after the ledger confirms it. If compensation cannot be confirmed, status becomes `REQUIRES_REVIEW` and staff can use the recovery action.

Admin-only deterministic scenarios are available in **Transfer money**. They are test controls, not customer options.

## Demo policies

- Savings minimum balance: ₹1,000.
- Daily outgoing transfer limit: ₹25,000 per source account.
- Max request amount: ₹1,00,000 for this educational demo.
- The application starts empty; accounts are created only through approved applications.

## Security and limitations

- Passwords are salted and hashed using Python `scrypt`; JWT access tokens expire after 15 minutes.
- Customer ownership and role checks are enforced in the service APIs.
- The bootstrap endpoint can only create an admin while no admin exists. Rotate/remove the bootstrap secret after setup.
- Logout in this MVP removes the token from the browser; there is no server-side token revocation or refresh-token rotation.
- Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` in `.env` before customer registration. Gmail requires an App Password with 2-Step Verification enabled. Email OTPs expire after five minutes.
- Google sign-in is optional. Create a Google OAuth Web Client, allow `http://localhost:5173`, set `GOOGLE_CLIENT_ID` in `.env`, then rebuild the frontend. Google login is only for customer accounts; transfers still require email OTP.
- Branch managers and employees are scoped to their assigned branch for application, deposit, account and transaction views/actions; Admin can view all branches. Existing staff tokens must be refreshed by signing in again after a role/branch change.
- Fixed deposits use an educational 6.5% simple-interest estimate and manual maturity payout; loan approval/disbursement is a demo flow without EMI schedule, credit scoring or repayment collection. Do not treat either as a real bank product.
- Each service has an independent persistent SQLite database for easy one-command local deployment. The ledger service records idempotent financial postings but this MVP does not yet implement a full double-entry accounting model, transactional outbox, automated reconciliation, robust concurrent debit locking, or a production-grade distributed recovery worker. Do not use for real money or customer data.
- Full Docker build/runtime tests should be run on the target machine; this packaging environment could not complete npm dependency installation or a Docker build, so browser end-to-end behavior remains unverified.


## Merged Saga recovery
This build includes a scheduled stale-Saga recovery worker. It scans in-flight transfers after a configurable grace period, checks whether the deterministic destination-credit posting exists, and either safely attempts idempotent compensation or escalates ambiguous cases to `REQUIRES_REVIEW`. See `MERGED_REQUIREMENTS_AND_LIMITATIONS.md` for behavior and remaining production limitations.

# BankingTransactionManagementSystem
A software system for managing customer accounts, banking transactions, deposits, withdrawals, fund transfers, and transaction records.
