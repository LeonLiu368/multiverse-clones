def test_get_file_shape(client):
    r = client.get(f"/v1/files/{client.file_key}")
    assert r.status_code == 200
    d = r.json()
    assert d["document"]["type"] == "DOCUMENT"
    assert d["name"] == "Design System"
    assert "components" in d and "styles" in d and "schemaVersion" in d


def test_auth_required(client):
    # the fixture client sends a token; a bare request without one is rejected
    r = client.get(f"/v1/files/{client.file_key}", headers={"X-Figma-Token": ""})
    assert r.status_code == 403
    assert r.json() == {"status": 403, "err": "Invalid token"}


def test_file_not_found(client):
    r = client.get("/v1/files/doesnotexist000000000")
    assert r.status_code == 404
    assert r.json() == {"status": 404, "err": "Not found"}


def test_get_nodes(client):
    r = client.get(f"/v1/files/{client.file_key}/nodes", params={"ids": "1:19"})
    assert r.status_code == 200
    node = r.json()["nodes"]["1:19"]["document"]
    assert node["name"] == "PricingCard"
    assert node["cornerRadius"] == 8


def test_nodes_hyphen_form(client):
    # deep-link hyphen form (1-19) is accepted and normalized to 1:19
    r = client.get(f"/v1/files/{client.file_key}/nodes", params={"ids": "1-19"})
    assert r.json()["nodes"]["1:19"]["document"]["name"] == "PricingCard"


def test_comments_post_read_back(client):
    key = client.file_key
    before = client.get(f"/v1/files/{key}/comments").json()["comments"]
    created = client.post(f"/v1/files/{key}/comments",
                          json={"message": "done", "client_meta": {"node_id": "1:19"}}).json()
    assert created["message"] == "done"
    assert created["client_meta"]["node_id"] == "1:19"
    after = client.get(f"/v1/files/{key}/comments").json()["comments"]
    assert len(after) == len(before) + 1
    assert any(c["id"] == created["id"] for c in after)


def test_components_and_styles(client):
    key = client.file_key
    comps = client.get(f"/v1/files/{key}/components").json()["meta"]["components"]
    assert {c["name"] for c in comps} >= {"PricingCard", "Primary"}
    styles = client.get(f"/v1/files/{key}/styles").json()["meta"]["styles"]
    assert any(s["name"] == "Primary/500" for s in styles)


def test_versions(client):
    vs = client.get(f"/v1/files/{client.file_key}/versions").json()["versions"]
    assert len(vs) == 2


def test_images(client):
    r = client.get(f"/v1/images/{client.file_key}", params={"ids": "1:19,9:99"})
    d = r.json()
    assert d["err"] is None
    assert d["images"]["1:19"].endswith("/static/" + client.file_key + "/1-19.png")
    assert d["images"]["9:99"] is None  # unknown node → None


def test_projects(client):
    d = client.get("/v1/teams/T1/projects").json()
    assert d["name"] == "Acme Design"
    assert d["projects"][0]["id"] == "P1"
    files = client.get("/v1/projects/P1/files").json()["files"]
    assert files[0]["key"] == client.file_key


def test_determinism():
    from figmaclone.seed import schema
    from figmaclone.seed.generator import generate

    assert schema.to_json(generate(seed=7)) == schema.to_json(generate(seed=7))
