# SEC-01 RISK ACCEPTANCE TEMPLATE

Use only if the project owner chooses to go live without upgrading Supabase to a plan that supports leaked-password protection.

## Risk

Supabase security advisor reports:
```text
auth_leaked_password_protection
```

The current organization plan does not provide the control.

## Compensating controls

Confirm:
- [ ] strong password policy is communicated/enforced operationally
- [ ] production credentials are not shared
- [ ] privileged ADMIN access is restricted
- [ ] leaked-password protection will be reconsidered on plan upgrade
- [ ] auth logs/security incidents are reviewed when relevant
- [ ] no SQL workaround is introduced

## Acceptance

```text
Project:
AI Piutang Vouching

Risk:
Leaked-password detection is not enabled on the current Supabase plan.

Decision:
[ ] ACCEPT temporarily
[ ] DO NOT ACCEPT — upgrade plan before go-live

Owner:
____________________

Role:
____________________

Date:
____________________

Review/expiry date:
____________________

Notes:
____________________
```

Attach the completed decision to GO-LIVE #103 without credentials or secrets.
