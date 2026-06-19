from pkg.sql.rowenc.partition_tuple_guard import should_guard_partition_tuple


def classify_descriptor_case(row):
    if should_guard_partition_tuple(row):
        return {
            "id": row["case_id"],
            "reason": "guard empty partition tuple decode for CRDB-63642",
            "source": "sentry_7461557230/postgres",
        }
    return None
