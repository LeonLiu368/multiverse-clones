# Plaid/OAuth Link — QA Flow Checklist

Canonical flow identifiers for the linking QA matrix live in this table. Flow ids are
stable and used verbatim by `linking/coverage.py` and the QA tooling; **statuses below were
last reviewed 2026-05-20 and are known to have drifted** — see #oauth-rollout for the
current rollout state before trusting any status or flag in this file.

| flow id | status (stale) | update_mode | requires_device | notes |
|---|---|---|---|---|
| `fund_account_default_onetime` | covered | no | no | FundAccount default one-time |
| `fund_account_control` | blocked on test fixtures | no | no | FundAccount control flows |
| `fund_account_recurring` | not planned this release | no | no | FundAccount recurring |
| `linked_accounts_add_account` | covered | no | no | LinkedAccounts add new account |
| `liability_bill_link` | in progress | yes | no | link liability accounts to create bills |
| `counterparty_relink_update` | covered | no | no | re-link counterparty accounts |
| `liability_relink_update` | in progress | no | no | re-link liability accounts |
| `microdeposit_verify_update` | not planned this release | no | no | verify microdeposit amounts |
| `oauth_normal` | covered | no | no | standard OAuth linking |
| `oauth_app_to_app_chase` | covered | no | yes | superseded id — kept for history |
| `oauth_app_to_app_chase_device` | pending device run | no | no | Chase app-to-app on device |
| `oauth_app_to_app_chase_device_validation` | proposed | no | no | proposal only, never shipped |
| `linked_accounts_bulk_import` | cancelled | no | no | cancelled 2026-04 |

Deprecated/never-shipped rows (`oauth_app_to_app_chase`,
`oauth_app_to_app_chase_device_validation`, `linked_accounts_bulk_import`) must not be
added to the required matrix.
