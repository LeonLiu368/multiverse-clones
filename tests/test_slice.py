from __future__ import annotations
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from spoink.slice import slice_export, parse_cutoff, parse_tz  # noqa: E402


def _write(d, channel, msgs):
    (d / channel).mkdir(parents=True)
    (d / "channels.json").write_text(json.dumps([{"id": "C1", "name": channel}]))
    (d / "users.json").write_text("[]")
    from collections import defaultdict
    from datetime import datetime, timezone
    byday = defaultdict(list)
    for m in msgs:
        byday[datetime.fromtimestamp(float(m["ts"]), tz=timezone.utc).strftime("%Y-%m-%d")].append(m)
    for day, ms in byday.items():
        (d / channel / f"{day}.json").write_text(json.dumps(ms))


def test_parse_tz_and_cutoff():
    assert parse_tz("-7").total_seconds() == -7 * 3600
    assert parse_tz("-07:00").total_seconds() == -7 * 3600
    assert parse_tz("+0530").total_seconds() == 5.5 * 3600
    # 2026-06-24 17:34 PDT (-7) == 2026-06-25 00:34 UTC
    from datetime import datetime, timezone
    assert parse_cutoff("2026-06-24 17:34", "-7") == datetime(2026, 6, 25, 0, 34, tzinfo=timezone.utc).timestamp()


def test_slice_filters_by_cutoff(tmp_path):
    src = tmp_path / "src"
    msgs = [{"ts": f"{t}.000000", "user": "U1", "text": str(t)} for t in
            (1700000000, 1700000100, 1700000200, 1700000300)]
    _write(src, "general", msgs)
    res = slice_export(str(src), str(tmp_path / "out"), cutoff=1700000150.0)
    assert res["kept"] == 2 and res["dropped"] == 2
    assert res["last_kept"]["ts"] == "1700000100.000000"
    assert res["first_dropped"]["ts"] == "1700000200.000000"
    # roster carried over; sliced dir still has the standard layout
    assert (tmp_path / "out" / "users.json").exists()
    assert (tmp_path / "out" / "channels.json").exists()
    kept = [m for f in (tmp_path / "out" / "general").glob("*.json") for m in json.load(open(f))]
    assert len(kept) == 2
