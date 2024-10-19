import os

from tests.utils import create_new_user, new_user_password, agent_id


def test_call(secure_client, secure_client_headers):
    response = secure_client.get("/static/", headers=secure_client_headers)
    assert response.status_code == 404


def test_call_by_jwt(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"STATIC": ["READ"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = res.json()["access_token"]

    response = client.get("/static/", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    assert response.status_code == 404

    # insert a new file in static folder
    static_file_name = "Meooow.txt"
    static_file_path = f"/app/cat/static/{static_file_name}"
    with open(static_file_path, "w") as f:
        f.write("Meow")

    response = client.get(
        f"/static/{static_file_name}", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id}
    )
    assert response.status_code == 200

    os.remove(static_file_path)


def test_forbidden_call_by_jwt(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"STATIC": ["WRITE"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = res.json()["access_token"]

    response = client.get("/static/", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    assert response.status_code == 403


def test_call_specific_file(secure_client, secure_client_headers):
    static_file_name = "Meooow.txt"
    static_file_path = f"/app/cat/static/{static_file_name}"

    # ask for inexistent file
    response = secure_client.get(f"/static/{static_file_name}", headers=secure_client_headers)
    assert response.status_code == 404

    # insert file in static folder
    with open(static_file_path, "w") as f:
        f.write("Meow")

    response = secure_client.get(f"/static/{static_file_name}", headers=secure_client_headers)
    assert response.status_code == 200

    os.remove(static_file_path)
