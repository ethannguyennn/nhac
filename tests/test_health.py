def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


def test_index_page(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Relive the moment" in resp.text
