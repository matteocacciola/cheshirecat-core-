import pytest
from pydantic import ValidationError

from cat.auth.permissions import get_full_admin_permissions
from cat.env import get_env
from cat.routes.admins.crud import AdminBase, AdminUpdate

from tests.utils import create_new_user, check_user_fields, get_client_admin_headers, new_user_password


def test_validation_errors():
    with pytest.raises(ValidationError) as e:
        AdminBase(username="Alice", permissions={})

    admin = AdminUpdate(username="Alice")
    assert isinstance(admin, AdminUpdate)
    assert admin.username == "Alice"

    with pytest.raises(ValidationError) as e:
        AdminUpdate(username="Alice", permissions={})
    with pytest.raises(ValidationError) as e:
        AdminUpdate(username="Alice", permissions={"READ": []})
    with pytest.raises(ValidationError) as e:
        AdminUpdate(username="Alice", permissions={"CHESHIRE_CATS": []})
    with pytest.raises(ValidationError) as e:
        AdminUpdate(username="Alice", permissions={"CHESHIRE_CATS": ["WRITE", "WRONG"]})

def test_create_admin(client):
    # create admin
    data = create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))

    # assertions on admin structure
    check_user_fields(data)

    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()


def test_cannot_create_duplicate_admin(client):
    # create admin
    create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))

    # create admin with same username
    response = client.post(
        "/admins/users", json={"username": "Alice", "password": "ecilA"}, headers=get_client_admin_headers(client)
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Cannot duplicate admin"


def test_get_admins(client):
    # get list of admins
    response = client.get("/admins/users", headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    # create admin
    create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))

    # get updated list of admins
    response = client.get("/admins/users", headers=get_client_admin_headers(client))
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
    response = client.get("/admins/users/wrong_admin_id", headers=get_client_admin_headers(client))
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))["id"]

    # get specific existing admin
    response = client.get(f"/admins/users/{admin_id}", headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()

    # check admin integrity and values
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()


def test_update_admin(client):
    # update unexisting admin
    response = client.put(
        "/admins/users/non_existent_id", json={"username": "Red Queen"}, headers=get_client_admin_headers(client)
    )
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))["id"]

    # update unexisting attribute (bad request)
    updated_admin = {"username": "Alice", "something": 42}
    response = client.put(f"/admins/users/{admin_id}", json=updated_admin, headers=get_client_admin_headers(client))
    assert response.status_code == 400

    # change nothing
    response = client.put(f"/admins/users/{admin_id}", json={}, headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()

    # nothing changed so far
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()

    # update password
    updated_admin = {"password": "12345"}
    response = client.put(f"/admins/users/{admin_id}", json=updated_admin, headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_full_admin_permissions()
    assert "password" not in data # api will not send passwords around

    # change username
    updated_admin = {"username": "Alice2"}
    response = client.put(f"/admins/users/{admin_id}", json=updated_admin, headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == get_full_admin_permissions()

    # change permissions
    updated_admin = {"permissions": {"EMBEDDER": ["READ"]}}
    response = client.put(f"/admins/users/{admin_id}", json=updated_admin, headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == {"EMBEDDER": ["READ"]}

    # change username and permissions
    updated_admin = {"username": "Alice3", "permissions": {"EMBEDDER": ["WRITE"]}}
    response = client.put(f"/admins/users/{admin_id}", json=updated_admin, headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice3"
    assert data["permissions"] == {"EMBEDDER": ["WRITE"]}

    # get list of admins
    response = client.get("/admins/users", headers=get_client_admin_headers(client))
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
    response = client.delete("/admins/users/non_existent_id", headers=get_client_admin_headers(client))
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create admin and obtain id
    admin_id = create_new_user(client, "/admins/users", headers=get_client_admin_headers(client))["id"]

    # delete admin
    response = client.delete(f"/admins/users/{admin_id}", headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == admin_id

    # check that the admin is not in the db anymore
    response = client.get(f"/admins/users/{admin_id}", headers=get_client_admin_headers(client))
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # check admin is no more in the list of admins
    response = client.get("/admins/users", headers=get_client_admin_headers(client))
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["username"] == "admin"


# note: using secure client (api key set both for http and ws)
def test_no_access_if_api_keys_active(secure_client):
    # create admin (forbidden)
    response = secure_client.post(
        "/admins/users",
        json={"username": "Alice", "password": new_user_password},
    )
    assert response.status_code == 403

    # read admins (forbidden)
    response = secure_client.get("/admins/users")
    assert response.status_code == 403

    # edit admin (forbidden)
    response = secure_client.put(
        "/admins/users/non_existent_id", # it does not exist, but request should be blocked before the check
        json={"username": "Alice"},
    )
    assert response.status_code == 403

    # check default list giving the correct CCAT_API_KEY
    headers = {"Authorization": f"Bearer {get_env('CCAT_API_KEY')}"}
    response = secure_client.get("/admins/users", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["username"] == "admin"
