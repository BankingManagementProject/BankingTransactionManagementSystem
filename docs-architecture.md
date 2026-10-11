# Architecture and Activity Flows

```mermaid
flowchart TD
  Browser --> Gateway[Nginx API Gateway]
  Gateway --> Identity[Identity Service]
  Gateway --> Account[Account & Approval Service]
  Gateway --> Txn[Transaction & Saga Service]
  Txn --> Account
  Account --> Ledger[Ledger Service]
  Txn --> Ledger
  Identity --> IDDB[(identity_data)]
  Account --> ADB[(account_data)]
  Txn --> TDB[(transaction_data)]
  Ledger --> LDB[(ledger_data)]
  Txn --> MQ[RabbitMQ Events]
```

## Transfer activity

```mermaid
flowchart TD
  A[Transfer requested] --> B[PENDING]
  B --> C[VALIDATING]
  C --> D{Destination exists and policies pass?}
  D -- No --> E[VALIDATION_FAILED]
  D -- Yes --> F[VALIDATED]
  F --> G[Ledger debit]
  G --> H{Debit confirmed?}
  H -- No --> I[FAILED]
  H -- Yes --> J[DEBIT_CONFIRMED]
  J --> K[Credit destination]
  K --> L{Credit confirmed?}
  L -- Yes --> M[SUCCESS]
  L -- No --> N[CREDIT_FAILED]
  N --> O[COMPENSATING]
  O --> P{Source reversal confirmed?}
  P -- Yes --> Q[COMPENSATED]
  P -- No --> R[REQUIRES_REVIEW]
  R --> S[Staff investigates and records recovery]
  S --> Q
```

A timeline contains only persisted stages reached by the transaction. Validation failures do not fabricate debit/credit or compensation events.


## Added modules
- Notification Service: independent SQLite store for short-lived OTP challenges; SMTP sends customer email-verification codes and transfer authorization codes. The transfer service verifies and consumes OTP internally before starting a customer transfer. SMTP secrets are supplied through `.env`.
- Branch ownership: staff identity tokens carry a branch claim; account-service filters staff queues and enforces branch matching for employee/manager operations. Admin is the cross-branch role.
- Fixed deposits: principal is debited from an existing account, the fixed-deposit record tracks a chosen term and maturity date, and a manual maturity action credits principal plus a demo simple-interest estimate.
- Loans: customer loan applications are scoped to a branch and require manager/admin approval before a demo ledger credit. Repayment/EMI functionality is intentionally outside this MVP.
- Optional Google Identity Services login: configured with `GOOGLE_CLIENT_ID`; the identity service validates the returned credential against Google's tokeninfo endpoint and requires a verified email.
