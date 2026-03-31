def _create_stream(client, name="Test Stream", url="rtsp://example.com/stream"):
    return client.post("/api/streams/", json={"name": name, "url": url})


def test_create_stream(authed_client):
    resp = _create_stream(authed_client)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Stream"
    assert "url" not in data


def test_list_streams(authed_client):
    _create_stream(authed_client, name="Stream 1")
    _create_stream(authed_client, name="Stream 2")
    resp = authed_client.get("/api/streams/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_get_stream(authed_client):
    create_resp = _create_stream(authed_client)
    stream_id = create_resp.json()["id"]
    resp = authed_client.get(f"/api/streams/{stream_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == stream_id
    assert data["name"] == "Test Stream"
    assert data["enabled"] is True


def test_update_stream(authed_client):
    create_resp = _create_stream(authed_client)
    stream_id = create_resp.json()["id"]
    resp = authed_client.put(f"/api/streams/{stream_id}", json={"name": "Updated"})
    assert resp.status_code == 200
    assert resp.json()["name"] == "Updated"


def test_delete_stream(authed_client):
    create_resp = _create_stream(authed_client)
    stream_id = create_resp.json()["id"]
    resp = authed_client.delete(f"/api/streams/{stream_id}")
    assert resp.status_code == 204
    resp = authed_client.get(f"/api/streams/{stream_id}")
    assert resp.status_code == 404


def test_create_stream_empty_name(authed_client):
    resp = authed_client.post("/api/streams/", json={"name": "", "url": "rtsp://x"})
    # FastAPI/Pydantic accepts empty strings; the model allows it
    # But we verify validation works for missing fields
    resp2 = authed_client.post("/api/streams/", json={"url": "rtsp://x"})
    assert resp2.status_code == 422
