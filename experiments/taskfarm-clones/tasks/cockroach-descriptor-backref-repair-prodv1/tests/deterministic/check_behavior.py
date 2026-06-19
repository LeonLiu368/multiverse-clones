from catalog_repair.planner import plan_repairs


rows = [
    {
        "relation_id": 700,
        "relation_name": "public_live_missing",
        "descriptor_kind": "relation",
        "relation_state": "public",
        "referenced_descriptor_id": 900,
        "referenced_exists": False,
        "stack_key": "sql.schema.validation_errors.read.backward_references.relation",
    },
    {
        "relation_id": 701,
        "relation_name": "public_live_existing",
        "descriptor_kind": "relation",
        "relation_state": "public",
        "referenced_descriptor_id": 901,
        "referenced_exists": True,
        "stack_key": "sql.schema.validation_errors.read.backward_references.relation",
    },
    {
        "relation_id": 702,
        "relation_name": "dropped_missing",
        "descriptor_kind": "relation",
        "relation_state": "dropped",
        "referenced_descriptor_id": 902,
        "referenced_exists": False,
        "stack_key": "sql.schema.validation_errors.read.backward_references.relation",
    },
    {
        "relation_id": 703,
        "relation_name": "column_missing",
        "descriptor_kind": "column",
        "relation_state": "public",
        "referenced_descriptor_id": 903,
        "referenced_exists": False,
        "stack_key": "sql.schema.validation_errors.read.backward_references.relation",
    },
    {
        "relation_id": 704,
        "relation_name": "forward_ref_missing",
        "descriptor_kind": "relation",
        "relation_state": "public",
        "referenced_descriptor_id": 904,
        "referenced_exists": False,
        "stack_key": "sql.schema.validation_errors.write.forward_references.sequence",
    },
]

repairs = plan_repairs(rows)
assert [repair.relation_id for repair in repairs] == [700], repairs
repair = repairs[0]
assert repair.referenced_descriptor_id == 900
assert repair.action == "remove_depended_on_by_backref"
assert "missing" in repair.reason.lower() or "not found" in repair.reason.lower(), repair.reason
print("behavior ok")
