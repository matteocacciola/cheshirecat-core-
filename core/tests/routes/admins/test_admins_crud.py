from cat.auth.permissions import get_full_admin_permissions
from cat.env import get_env

from tests.utils import create_new_user, check_user_fields


def test_create_admin(client):
    # create admin
    data = create_new_user(client, "/admins")

    # assertions on admin structure
    check_user_fields(data)

    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()


def test_cannot_create_duplicate_admin(client):
    # create admin
    create_new_user(client, "/admins")

    # create admin with same username
    response = client.post("/admins", json={"username": "Alice", "password": "ecilA"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Cannot duplicate admin"


def test_get_admins(client):
    # get list of admins
    response = client.get("/admins")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    # create admin
    create_new_user(client, "/admins")

    # get updated list of admins
    response = client.get("/admins")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # check admins integrity and values
    for idx, d in enumerate(data):
        check_user_fields(d)
        assert d["username"] in ["admin", "Alice"]
        assert d["permissions"] == get_full_admin_permissions()


def test_get_admin(client):
    # get unexisting admin
    response = client.get("/admins/wrong_admin_id")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins")["id"]

    # get specific existing admin
    response = client.get(f"/admins/{admin_id}")
    assert response.status_code == 200
    data = response.json()

    # check admin integrity and values
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()


def test_update_admin(client):
    # update unexisting admin
    response = client.put("/admins/non_existent_id", json={"username": "Red Queen"})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins")["id"]

    # update unexisting attribute (bad request)
    updated_admin = {"username": "Alice", "something": 42}
    response = client.put(f"/admins/{admin_id}", json=updated_admin)
    assert response.status_code == 400

    # change nothing
    response = client.put(f"/admins/{admin_id}", json={})
    assert response.status_code == 200
    data = response.json()

    # nothing changed so far
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()

    # update password
    updated_admin = {"password": "12345"}
    response = client.put(f"/admins/{admin_id}", json=updated_admin)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()
    assert "password" not in data # api will not send passwords around

    # change username
    updated_admin = {"username": "Alice2"}
    response = client.put(f"/admins/{admin_id}", json=updated_admin)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == get_full_admin_permissions()

    # change permissions
    updated_admin = {"permissions": {"EMBEDDER": ["READ"]}}
    response = client.put(f"/admins/{admin_id}", json=updated_admin)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == {"EMBEDDER": ["READ"]}

    # change username and permissions
    updated_admin = {"username": "Alice3", "permissions": {"EMBEDDER": ["WRITE"]}}
    response = client.put(f"/admins/{admin_id}", json=updated_admin)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice3"
    assert data["permissions"] == {"EMBEDDER": ["WRITE"]}

    # get list of admins
    response = client.get("/admins")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for d in data:
        check_user_fields(d)
        assert d["username"] in ["admin", "Alice3"]
        if d["username"] == "Alice3":
            assert d["permissions"] == {"EMBEDDER": ["WRITE"]}
        else:
            assert d["permissions"] == get_full_admin_permissions()


def test_delete_admin(client):
    # delete unexisting admin
    response = client.delete("/admins/non_existent_id")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins")["id"]

    # delete admin
    response = client.delete(f"/admins/{admin_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == admin_id

    # check that the admin is not in the db anymore
    response = client.get(f"/admins/{admin_id}")
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # check admin is no more in the list of admins
    response = client.get("/admins")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["username"] == "admin"


# note: using secure client (api key set both for http and ws)
def test_no_access_if_api_keys_active(secure_client):
    # create admin (forbidden)
    response = secure_client.post(
        "/admins",
        json={"username": "Alice", "password": "wandering_in_wonderland"}
    )
    assert response.status_code == 403

    # read admins (forbidden)
    response = secure_client.get("/admins")
    assert response.status_code == 403

    # edit admin (forbidden)
    response = secure_client.put(
        "/admins/non_existent_id", # it does not exist, but request should be blocked before the check
        json={"username": "Alice"}
    )
    assert response.status_code == 403

    # check default list giving the correct CCAT_API_KEY
    headers = {"Authorization": f"Bearer {get_env('CCAT_API_KEY')}"}
    response = secure_client.get("/admins", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["username"] == "admin"
