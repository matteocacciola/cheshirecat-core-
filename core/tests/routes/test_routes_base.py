def test_ping_success(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "We're all mad here, dear!"


def test_ping_error(client):
    response = client.get("/", headers={"agent_id": "core"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Agent ID: \"core\" is reserved."
