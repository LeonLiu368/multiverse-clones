import os

import pytest
from fastapi.testclient import TestClient

from figmaclone.api.app import create_app
from figmaclone.seed.generator import generate
from figmaclone.seed.load import load_seed


@pytest.fixture()
def seeded_db(tmp_path):
    db = str(tmp_path / "figma.db")
    sd = generate(seed=42)
    load_seed(sd, db)
    key = sd["files"][0]["key"]
    return db, key


@pytest.fixture()
def client(seeded_db):
    db, key = seeded_db
    os.environ["FIGMA_REQUIRE_TOKEN"] = "1"
    app = create_app(db)
    c = TestClient(app, headers={"X-Figma-Token": "t"})
    c.file_key = key  # type: ignore[attr-defined]
    c.figma_app = app  # type: ignore[attr-defined]
    yield c
    c.close()
