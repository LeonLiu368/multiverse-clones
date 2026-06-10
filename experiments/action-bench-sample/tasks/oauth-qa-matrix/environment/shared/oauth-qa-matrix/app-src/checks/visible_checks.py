from linking.coverage import required_flows, coverage_summary, qa_matrix

flows = set(required_flows())
assert "fund_account_default_onetime" in flows
assert "linked_accounts_add_account" in flows
assert "oauth_normal" in flows
assert "oauth_app_to_app_chase_device" in flows
assert "oauth_app_to_app_chase" not in flows
assert "oauth_app_to_app_chase_device_validation" not in flows
rows = {row["flow"]: row for row in qa_matrix()}
assert rows["oauth_app_to_app_chase_device"]["requires_device"] is True
summary = coverage_summary()
assert isinstance(summary["total_flows"], int)
assert "oauth_app_to_app_chase_device" in summary["device_required_flows"]
print("oauth visible checks passed")
