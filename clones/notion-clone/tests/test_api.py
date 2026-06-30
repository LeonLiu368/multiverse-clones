"""Endpoint coverage (R6.1): every covered endpoint, happy path + >=1 error path,
plus the query-grammar and the write->read round-trip (R5.2)."""

from __future__ import annotations

UNKNOWN = "00000000-0000-4000-8000-000000000999"


# ----------------------------------------------------------------- meta / users
def test_health(client):
    assert client.get("/health").json()["status"] == "healthy"


def test_unauthorized_without_token(live_server):
    import httpx
    r = httpx.get(f"{live_server}/v1/users")  # no Authorization header
    assert r.status_code == 401
    assert r.json()["code"] == "unauthorized"


def test_users_list(client):
    r = client.get("/v1/users").json()
    assert r["object"] == "list"
    assert all(u["object"] == "user" for u in r["results"])
    assert len(r["results"]) >= 5


def test_users_retrieve(client, ids):
    r = client.get(f"/v1/users/{ids['user_id']}").json()
    assert r["object"] == "user" and r["id"] == ids["user_id"]


def test_users_retrieve_404(client):
    r = client.get(f"/v1/users/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == "object_not_found"


def test_users_me(client):
    r = client.get("/v1/users/me").json()
    assert r["object"] == "user" and r["type"] == "bot"


# ----------------------------------------------------------------- pages
def test_page_retrieve(client, ids):
    r = client.get(f"/v1/pages/{ids['task_page_id']}").json()
    assert r["object"] == "page"
    assert r["parent"]["database_id"] == ids["database_id"]


def test_page_retrieve_404(client):
    r = client.get(f"/v1/pages/{UNKNOWN}")
    assert r.status_code == 404 and r.json()["code"] == "object_not_found"


def test_page_create_in_database(client, ids):
    props = {"Name": {"type": "title", "title": [{"type": "text", "text": {"content": "New task"}}]},
             "Estimate": {"type": "number", "number": 4},
             "Status": {"type": "status", "status": {"name": "Backlog"}}}
    r = client.post("/v1/pages", json={"parent": {"type": "database_id", "database_id": ids["database_id"]},
                                       "properties": props}).json()
    assert r["object"] == "page" and r["id"]
    # read it back
    back = client.get(f"/v1/pages/{r['id']}").json()
    assert back["properties"]["Estimate"]["number"] == 4


def test_page_create_missing_parent_400(client):
    r = client.post("/v1/pages", json={"properties": {}})
    assert r.status_code == 400 and r.json()["code"] == "validation_error"


def test_page_create_bad_database_404(client):
    r = client.post("/v1/pages", json={"parent": {"type": "database_id", "database_id": UNKNOWN},
                                       "properties": {"Name": {"title": []}}})
    assert r.status_code == 404


def test_page_update_properties(client, ids):
    r = client.patch(f"/v1/pages/{ids['task_page_id']}",
                     json={"properties": {"Estimate": {"type": "number", "number": 99}}}).json()
    assert r["properties"]["Estimate"]["number"] == 99


def test_page_update_404(client):
    r = client.patch(f"/v1/pages/{UNKNOWN}", json={"properties": {}})
    assert r.status_code == 404


def test_page_archive_roundtrip(client, ids):
    # create a throwaway page, archive it, confirm archived
    props = {"Name": {"type": "title", "title": [{"type": "text", "text": {"content": "tmp"}}]}}
    pid = client.post("/v1/pages", json={"parent": {"database_id": ids["database_id"]},
                                         "properties": props}).json()["id"]
    arch = client.patch(f"/v1/pages/{pid}", json={"archived": True}).json()
    assert arch["archived"] is True
    assert client.get(f"/v1/pages/{pid}").json()["archived"] is True


# ----------------------------------------------------------------- blocks
def test_block_children(client, ids):
    r = client.get(f"/v1/blocks/{ids['doc_page_id']}/children").json()
    assert r["object"] == "list"
    assert all(b["object"] == "block" for b in r["results"])
    assert len(r["results"]) >= 1


def test_block_children_404(client):
    r = client.get(f"/v1/blocks/{UNKNOWN}/children")
    assert r.status_code == 404


def test_block_append(client, ids):
    children = [{"type": "paragraph", "paragraph": {"rich_text": [{"type": "text", "text": {"content": "appended"}}]}}]
    r = client.patch(f"/v1/blocks/{ids['doc_page_id']}/children", json={"children": children}).json()
    assert r["object"] == "list" and r["results"][0]["type"] == "paragraph"
    # round-trip: the appended block shows up in children
    kids = client.get(f"/v1/blocks/{ids['doc_page_id']}/children").json()["results"]
    assert any(b["id"] == r["results"][0]["id"] for b in kids)


def test_block_append_empty_400(client, ids):
    r = client.patch(f"/v1/blocks/{ids['doc_page_id']}/children", json={"children": []})
    assert r.status_code == 400


# ----------------------------------------------------------------- databases / query
def test_database_retrieve(client, ids):
    r = client.get(f"/v1/databases/{ids['database_id']}").json()
    assert r["object"] == "database"
    assert "Status" in r["properties"] and r["properties"]["Status"]["type"] == "status"


def test_database_retrieve_404(client):
    r = client.get(f"/v1/databases/{UNKNOWN}")
    assert r.status_code == 404


def test_query_no_filter(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query", json={}).json()
    assert r["object"] == "list" and len(r["results"]) >= 10


def test_query_status_filter(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"property": "Status", "status": {"equals": "Done"}}}).json()
    for p in r["results"]:
        assert p["properties"]["Status"]["status"]["name"] == "Done"
    assert len(r["results"]) >= 1


def test_query_number_comparison(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"property": "Estimate", "number": {"greater_than_or_equal_to": 8}}}).json()
    for p in r["results"]:
        assert p["properties"]["Estimate"]["number"] >= 8


def test_query_multiselect_contains(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"property": "Tags", "multi_select": {"contains": "bug"}}}).json()
    for p in r["results"]:
        names = [o["name"] for o in p["properties"]["Tags"]["multi_select"]]
        assert "bug" in names


def test_query_compound_and(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"and": [
                        {"property": "Done", "checkbox": {"equals": False}},
                        {"property": "Priority", "select": {"equals": "Urgent"}}]}}).json()
    for p in r["results"]:
        assert p["properties"]["Done"]["checkbox"] is False
        assert p["properties"]["Priority"]["select"]["name"] == "Urgent"


def test_query_sort(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"sorts": [{"property": "Estimate", "direction": "descending"}]}).json()
    ests = [p["properties"]["Estimate"]["number"] for p in r["results"]]
    assert ests == sorted(ests, reverse=True)


def test_query_pagination(client, ids):
    first = client.post(f"/v1/databases/{ids['database_id']}/query", json={"page_size": 5}).json()
    assert len(first["results"]) == 5 and first["has_more"] is True and first["next_cursor"]
    second = client.post(f"/v1/databases/{ids['database_id']}/query",
                         json={"page_size": 5, "start_cursor": first["next_cursor"]}).json()
    assert len(second["results"]) >= 1
    # no overlap
    ids1 = {p["id"] for p in first["results"]}
    ids2 = {p["id"] for p in second["results"]}
    assert ids1.isdisjoint(ids2)


def test_query_bad_operator_400(client, ids):
    r = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"property": "Estimate", "number": {"contains": 3}}})
    assert r.status_code == 400 and r.json()["code"] == "validation_error"


def test_query_404(client):
    r = client.post(f"/v1/databases/{UNKNOWN}/query", json={})
    assert r.status_code == 404


def test_query_writeread_roundtrip(client, ids):
    """R5.2: create a page with a distinctive property, then query and find it."""
    props = {"Name": {"type": "title", "title": [{"type": "text", "text": {"content": "Roundtrip probe"}}]},
             "Status": {"type": "status", "status": {"name": "In review"}},
             "Estimate": {"type": "number", "number": 13},
             "Tags": {"type": "multi_select", "multi_select": [{"name": "infra"}]}}
    created = client.post("/v1/pages", json={"parent": {"database_id": ids["database_id"]},
                                             "properties": props}).json()
    q = client.post(f"/v1/databases/{ids['database_id']}/query",
                    json={"filter": {"property": "Status", "status": {"equals": "In review"}},
                          "sorts": [{"property": "Estimate", "direction": "descending"}]}).json()
    found = [p for p in q["results"] if p["id"] == created["id"]]
    assert found, "newly created page not returned by the query — round-trip broken"
    assert found[0]["properties"]["Estimate"]["number"] == 13


# ----------------------------------------------------------------- search
def test_search_by_title(client):
    r = client.post("/v1/search", json={"query": "billing"}).json()
    assert r["object"] == "list"
    assert any("billing" in str(p).lower() for p in r["results"])


def test_search_filter_database(client):
    r = client.post("/v1/search", json={"query": "Tasks", "filter": {"property": "object", "value": "database"}}).json()
    assert all(p["object"] == "database" for p in r["results"])


def test_search_bad_filter_400(client):
    r = client.post("/v1/search", json={"filter": {"property": "object", "value": "widget"}})
    assert r.status_code == 400


# ----------------------------------------------------------------- comments
def test_comments_list(client, ids):
    r = client.get("/v1/comments", params={"block_id": ids["doc_page_id"]}).json()
    assert r["object"] == "list" and len(r["results"]) >= 2
    assert all(c["object"] == "comment" for c in r["results"])


def test_comments_list_missing_block_400(client):
    r = client.get("/v1/comments")
    assert r.status_code == 400


def test_comments_create_roundtrip(client, ids):
    r = client.post("/v1/comments", json={"parent": {"page_id": ids["doc_page_id"]},
                                          "rich_text": [{"type": "text", "text": {"content": "From the agent"}}]}).json()
    assert r["object"] == "comment"
    listed = client.get("/v1/comments", params={"block_id": ids["doc_page_id"]}).json()["results"]
    assert any(c["id"] == r["id"] for c in listed)


def test_comments_create_404(client):
    r = client.post("/v1/comments", json={"parent": {"page_id": UNKNOWN},
                                          "rich_text": [{"type": "text", "text": {"content": "x"}}]})
    assert r.status_code == 404


def test_comments_create_missing_rich_text_400(client, ids):
    r = client.post("/v1/comments", json={"parent": {"page_id": ids["doc_page_id"]}})
    assert r.status_code == 400
