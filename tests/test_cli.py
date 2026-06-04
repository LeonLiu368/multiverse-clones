import json
from pathlib import Path

from typer.testing import CliRunner

from slackclone.cli.main import app

runner = CliRunner()
FIX = Path(__file__).parent / "fixtures" / "tiny-export"


def _last_json(output: str) -> dict:
    return json.loads(output.strip().splitlines()[-1])


def test_seed_generate(tmp_path):
    db = tmp_path / "s.db"
    res = runner.invoke(app, ["seed", "generate", "--seed", "7", "--out", str(db),
                              "--users", "5", "--channels", "3", "--days", "4"])
    assert res.exit_code == 0, res.output
    out = _last_json(res.output)
    assert out["channels"] == 3 and out["messages"] > 0
    assert db.exists()


def test_seed_import_export(tmp_path):
    db = tmp_path / "i.db"
    res = runner.invoke(app, ["seed", "import-export", str(FIX), "--out", str(db)])
    assert res.exit_code == 0, res.output
    out = _last_json(res.output)
    assert out["channels"] == 2 and out["messages"] == 6


def test_seed_emit_and_load_roundtrip(tmp_path):
    ws = tmp_path / "workspace.json"
    db1 = tmp_path / "a.db"
    res = runner.invoke(app, ["seed", "import-export", str(FIX), "--out", str(db1), "--emit", str(ws)])
    assert res.exit_code == 0, res.output
    assert ws.exists()
    db2 = tmp_path / "b.db"
    res2 = runner.invoke(app, ["seed", "load", str(ws), "--out", str(db2)])
    assert res2.exit_code == 0, res2.output
    assert _last_json(res2.output)["messages"] == 6
