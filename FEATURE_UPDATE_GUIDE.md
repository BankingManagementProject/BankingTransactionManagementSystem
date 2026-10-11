# Northstar Bank feature update guide

## Added in this update

- Branch assignment on Admin-created Employee and Branch Manager identities.
- Branch-aware staff queries/actions for accounts, applications, deposits, transactions and loan review. Admin retains cross-branch access.
- Customer branch selector on account application form.
- Notification Service with expiring one-time codes sent through SMTP for customer email verification and transfer authorization.
- Google Identity Services login for customers when a Web OAuth Client ID is configured.
- Fixed deposit demo with principal lock/debit, selected tenure, maturity date, 6.5% simple-interest estimate, and maturity-only payout.
- Loan application/review/disbursement demo.
- Transaction timeline polling fix: background refresh no longer resets selected event history.

## Required email setup

Before registering a customer, edit `.env` and set:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-address@gmail.com
SMTP_PASSWORD=your-google-app-password
SMTP_FROM=your-address@gmail.com
SMTP_STARTTLS=true
```

For Gmail, enable 2-Step Verification and generate an App Password. Do not use your regular Google password. Restart after editing `.env`:

```powershell
docker compose up --build -d
```

Customer registration sends a six-digit verification code, valid for five minutes. Customer login is blocked until email verification. Every normal transfer requires a separate one-time email OTP, which is verified and consumed by the backend. OTPs are not printed to application logs.

## Optional Google sign-in setup

1. In Google Cloud Console, create an OAuth Client ID of type **Web application**.
2. Add `http://localhost:5173` to the authorized JavaScript origins.
3. Set `GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com` in `.env`.
4. Rebuild the frontend and services with `docker compose up --build -d`.

Google login is only for customer accounts. A Google-verified email can be used as email-verified identity; transfer OTP is still required.

## Branch assignment

When Admin creates an Employee or Branch Manager, select a branch. Customers choose the branch for each new account application. Employee and manager operations are restricted by the branch claim in their signed JWT and branch checks in the Account/Transaction services. Admin remains global. Sign out and back in after changing staff assignment so a fresh JWT is issued.

Available demo branches: Main Branch, Guntur Branch, Vijayawada Branch, Amaravati Branch, Visakhapatnam Branch, Hyderabad Branch.

## Fixed deposits and loans

- Fixed deposits debit principal from the customer's account and hold a record for a selected tenure. A customer can request payout only after maturity. The example uses 6.5% simple interest purely for demonstration; it is not a real bank rate.
- Loan requests are stored as `PENDING_REVIEW`. A manager/admin may approve and disburse the demo amount to the chosen customer account, or reject without disbursement. This does not include EMI scheduling, repayment collection, credit scoring, or regulatory lending checks.

## Validation performed here

- Python syntax compilation passed for all service modules.
- Each service's SQLite schema initialization passed.
- Notification OTP smoke test passed: valid OTP accepted once and replay rejected.
- Docker Compose YAML parsed successfully.
- Frontend TSX transpile syntax check passed.
- Full npm type-check/build and Docker/browser end-to-end tests could not be completed in this environment because npm dependencies could not be downloaded and Docker was unavailable. Run the documented smoke tests on the target machine before presenting the application.

This is an educational simulator, not a production banking system.
