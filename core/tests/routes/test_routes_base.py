import pytest

from tests.utils import get_client_admin_headers


def test_ping_success(secure_client, secure_client_headers):
    response = secure_client.get("/", headers=secure_client_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "We're all mad here, dear!"


def test_ping_success_by_admin_with_api_key(secure_client, secure_client_headers):
    headers = secure_client_headers | {"user_id": "admin"}

    response = secure_client.get("/", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "We're all mad here, dear!"


def test_ping_success_by_admin_with_token(client):
    headers = get_client_admin_headers(client)

    response = client.get("/", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "We're all mad here, dear!"
