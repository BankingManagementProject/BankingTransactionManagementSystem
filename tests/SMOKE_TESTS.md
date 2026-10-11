# Manual acceptance tests

Run these after `docker compose up --build -d`.

1. Open `http://localhost:5173`; verify no users/accounts/transactions are preloaded.
2. Use Initial administrator setup with `BANK_BOOTSTRAP_SECRET` from `.env`; register an admin and log in.
3. Create one Employee and one Manager in Staff access. Register two customer accounts using separate emails.
4. Customer A submits a SAVINGS application with initial deposit >= ₹1,000. Verify it as Employee, then approve it as Manager. Repeat for Customer B.
5. Confirm the accounts show their opening balances and `ACCOUNT_OPENING_DEPOSIT` history entries.
6. Customer A submits a ₹100 deposit. Verify the balance is unchanged while `PENDING_APPROVAL`. Approve it as Employee; verify balance increases and the transaction timeline reaches `SUCCESS`. Reject a separate deposit and verify no credit.
7. Customer A transfers to a nonexistent destination number. Expected timeline: `PENDING -> VALIDATING -> VALIDATION_FAILED`; no ledger balance changes.
8. Transfer to Customer B's active account. Expected final status `SUCCESS`, with `VALIDATED`, `DEBIT_CONFIRMED`, `CREDITING`, `CREDIT_CONFIRMED`, and `SUCCESS` events.
9. As Admin, use the Saga test runner for `FAIL_CREDIT_COMPENSATE`. Expected final status `COMPENSATED`, with a `COMPENSATING` event and restored source balance.
10. As Admin, use `FAIL_CREDIT_REVIEW`. Expected `REQUIRES_REVIEW`. As Employee, resolve it and confirm `COMPENSATED` only after the recovery ledger posting succeeds.
11. Log in as Customer A and try to access Customer B's accounts/transactions through the UI or API; the backend should not return Customer B's private data.
12. Restart with `docker compose restart`; confirm service data persists. Do not use `docker compose down -v` unless you want to erase all local data.

## Additional feature checks

- [ ] Configure SMTP in `.env`; register a new customer; confirm verification email arrives; verify code; confirm login works only after verification.
- [ ] Sign in as a verified customer, request a transfer OTP, enter the received code, and confirm one transfer is processed. Reusing the same OTP must fail.
- [ ] Create an Employee and Branch Manager assigned to `Guntur Branch`; confirm they see/review only Guntur applications, accounts and deposits. Create another branch's application and confirm it is not accessible to the first branch's staff. Confirm Admin can see both branches.
- [ ] Submit an account application to a branch different from Main Branch and confirm the created account retains that branch.
- [ ] Open a fixed deposit; verify principal is deducted from available balance; attempt closure before maturity and confirm it is blocked; after maturity, confirm payout includes the displayed educational simple-interest amount.
- [ ] Submit a loan application; confirm it remains pending until Manager/Admin action; reject it and confirm no disbursement, or approve it and confirm the demo credit is posted.
- [ ] Open a transaction timeline and leave the Transactions tab open through multiple refresh intervals; confirm event history does not blink/reset.
- [ ] If Google OAuth is configured, sign in with a Google customer account and confirm transfer OTP remains required.
