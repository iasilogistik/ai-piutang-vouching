# SECURITY RISK ACCEPTANCE TEMPLATE — SEC-01

> Template only. This document does **not** approve or accept risk by itself.

## Risk ID

SEC-01 — Supabase leaked-password protection is disabled.

## Current condition

- Production authentication is provided by Supabase Auth.
- Supabase Security Advisor reports `auth_leaked_password_protection`.
- The current Supabase organization plan is Free.
- Supabase leaked-password protection requires Pro or above.
- No SQL workaround is approved for this hosted Auth feature.

## Risk statement

If a user chooses a password that is already known to be compromised in public breach data, the current plan does not provide Supabase's leaked-password screening control. A compromised/reused password can increase the likelihood of unauthorized account access.

Application RBAC and branch isolation remain important authorization controls but do not eliminate credential-compromise risk.

## Preferred remediation

Upgrade the Supabase organization to a plan that supports leaked-password protection, enable the control, then rerun the Security Advisor and login regression tests.

## Temporary risk-acceptance option

If go-live proceeds before the plan upgrade, the project owner may explicitly accept the residual risk for a defined period.

Suggested compensating practices while the risk is accepted:
- prohibit shared application accounts;
- require unique, strong passwords through organizational policy;
- deactivate temporary UAT accounts after acceptance if no longer needed;
- reset credentials immediately if compromise/reuse is suspected;
- review Supabase Auth/security logs during incident investigation;
- retain normal ADMIN/AUDITOR/REVIEWER/VIEWER least-privilege mappings.

## Decision

Choose exactly one:

- [ ] **REMEDIATE BEFORE GO-LIVE** — upgrade plan and enable leaked-password protection.
- [ ] **TEMPORARY RISK ACCEPTANCE** — proceed with the control disabled until the review date below.
- [ ] **DO NOT GO LIVE** — defer production acceptance.

## Approval fields

- Project owner:
- Internal Audit owner:
- Decision date:
- Effective date:
- Review / expiry date:
- Rationale:
- Additional compensating controls:
- Evidence / ticket reference:

## Closure evidence

For remediation:
- Security Advisor no longer reports `auth_leaked_password_protection`.
- Login/refresh regression passes.

For temporary acceptance:
- completed decision fields;
- explicit owner approval;
- expiry/review date;
- reference attached to GO-LIVE #103 and SEC-01 #79.

Do not close SEC-01 based on this blank template.
