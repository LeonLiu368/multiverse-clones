import json

from slackclone.seed.generator import generate


def test_deterministic():
    a = generate(users=8, channels=5, days=7, seed=123)
    b = generate(users=8, channels=5, days=7, seed=123)
    assert json.dumps(a) == json.dumps(b)


def test_different_seeds_differ():
    a = generate(users=8, channels=5, days=7, seed=1)
    b = generate(users=8, channels=5, days=7, seed=2)
    assert json.dumps(a) != json.dumps(b)


def test_structure_threads_reactions_sorted():
    sd = generate(users=10, channels=4, days=6, seed=1)
    assert len(sd["users"]) == 11  # +1 bot
    assert len(sd["channels"]) == 4
    assert any(m["thread_ts"] for m in sd["messages"])  # has threads
    assert any(m["reactions"] for m in sd["messages"])  # has reactions
    ts = [float(m["ts"]) for m in sd["messages"]]
    assert ts == sorted(ts)  # chronological + unique
    assert len(ts) == len(set(ts))
