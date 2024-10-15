from cat.utils import DefaultAgentKeys


def test_ping_success(client, cheshire_cat):
    response = client.get("/", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    assert response.json()["status"] == "We're all mad here, dear!"


def test_ping_error(client):
    response = client.get("/")
    assert response.status_code == 404
