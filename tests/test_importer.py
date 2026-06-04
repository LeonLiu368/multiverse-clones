from pathlib import Path

from slackclone.seed.export_importer import import_export

FIX = Path(__file__).parent / "fixtures" / "tiny-export"


def test_import_reconstructs_channels_users_messages():
    sd = import_export(str(FIX))
    assert {c["name"] for c in sd["channels"]} == {"general", "incidents"}
    assert {u["name"] for u in sd["users"]} == {"alice", "bob", "incidentbot"}
    assert len(sd["messages"]) == 6  # 4 in general + 2 in incidents


def test_import_preserves_threads_reactions_subtypes_bots():
    sd = import_export(str(FIX))
    msgs = sd["messages"]
    reply = next(m for m in msgs if m["text"].startswith("yes, rolling back"))
    assert reply["thread_ts"] == "1704067260.000200"  # points at parent
    parent = next(m for m in msgs if m["ts"] == "1704067260.000200")
    assert parent["thread_ts"] is None  # parent's self-thread normalized away
    assert any(r["name"] == "eyes" for r in parent["reactions"])  # reaction preserved
    assert any(m.get("subtype") == "channel_join" for m in msgs)  # subtype preserved
    assert any(u["is_bot"] for u in sd["users"])  # bot flag preserved
