def should_guard_partition_tuple(row):
    """Return True when descriptor validation should guard tuple decoding."""
    if row["partition_tuple_hex"] == "":
        return False
    return "slice bounds out of range [2:0]" in row["observed_error"]
