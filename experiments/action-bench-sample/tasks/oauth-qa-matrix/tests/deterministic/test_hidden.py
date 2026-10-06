from linking.coverage import required_flows, qa_matrix, coverage_summary
expected = {
    "fund_account_default_onetime",
    "fund_account_control",
    "fund_account_recurring",
    "linked_accounts_add_account",
    "liability_bill_link",
    "counterparty_relink_update",
    "liability_relink_update",
    "microdeposit_verify_update",
    "oauth_normal",
    "oauth_app_to_app_chase_device",
}
flows = set(required_flows())
assert flows == expected, flows
rows = {row["flow"]: row for row in qa_matrix()}
assert all(rows[f].get("covered") is True for f in expected)
assert rows["oauth_app_to_app_chase_device"].get("requires_device") is True
update = {f for f, row in rows.items() if row.get("update_mode")}
assert update == {"counterparty_relink_update", "liability_relink_update", "microdeposit_verify_update"}, update
summary = coverage_summary()
assert summary["total_flows"] == 10
assert summary["missing_flows"] == []
assert summary["update_mode_flows"] == 3
assert summary["device_required_flows"] == ["oauth_app_to_app_chase_device"]
print("oauth hidden checks passed")
