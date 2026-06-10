REQUIRED_FLOWS = [
    "fund_account_default_onetime",
    "linked_accounts_add_account",
    "oauth_normal",
]

def required_flows():
    return list(REQUIRED_FLOWS)

def qa_matrix():
    return [{"flow": flow, "covered": True, "update_mode": False, "requires_device": False} for flow in required_flows()]

def coverage_summary():
    matrix = qa_matrix()
    return {
        "total_flows": len(matrix),
        "missing_flows": [],
        "update_mode_flows": sum(1 for row in matrix if row.get("update_mode")),
        "device_required_flows": [row["flow"] for row in matrix if row.get("requires_device")],
    }
