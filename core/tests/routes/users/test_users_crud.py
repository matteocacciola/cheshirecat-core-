import pytest
from pydantic import ValidationError

from cat.auth.permissions import get_base_permissions
from cat.routes.users import UserBase, UserUpdate

from tests.utils import agent_id, api_key, create_new_user, check_user_fields, new_user_password


def test_validation_errors():
    with pytest.raises(ValidationError) as e:
        UserBase(username="A", permissions={})

    user = UserUpdate(username="Alice")
    assert isinstance(user, UserUpdate)
    assert user.username == "Alice"

    with pytest.raises(ValidationError) as e:
        UserUpdate(username="Alice", permissions={})
    with pytest.raises(ValidationError) as e:
        UserUpdate(username="Alice", permissions={"READ": []})
    with pytest.raises(ValidationError) as e:
        UserUpdate(username="Alice", permissions={"STATUS": []})
    with pytest.raises(ValidationError) as e:
        UserUpdate(username="Alice", permissions={"STATUS": ["WRITE", "WRONG"]})


def test_create_user(secure_client, secure_client_headers):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers)

    # assertions on user structure
    check_user_fields(data)

    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()


def test_cannot_create_duplicate_user(secure_client, secure_client_headers):
    # create user
    create_new_user(secure_client, "/users", headers=secure_client_headers)

    # create user with same username
    response = secure_client.post(
        "/users", json={"username": "Alice", "password": "ecilA"}, headers=secure_client_headers
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Cannot duplicate user"


def test_get_users(secure_client, secure_client_headers):
    # get list of users
    response = secure_client.get("/users", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1 # user

    # create user
    create_new_user(secure_client, "/users", headers=secure_client_headers)

    # get updated list of users
    response = secure_client.get("/users", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    # check users integrity and values
    for idx, d in enumerate(data):
        check_user_fields(d)
        assert d["username"] in ["user", "Alice"]
        assert d["permissions"] == get_base_permissions()


def test_get_user(secure_client, secure_client_headers):
    # get unexisting user
    response = secure_client.get("/users/wrong_user_id", headers=secure_client_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(secure_client, "/users", headers=secure_client_headers)["id"]

    # get specific existing user
    response = secure_client.get(f"/users/{user_id}", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()

    # check user integrity and values
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()


def test_update_user(secure_client, secure_client_headers):
    # update unexisting user
    response = secure_client.put("/users/non_existent_id", json={"username": "Red Queen"}, headers=secure_client_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(secure_client, "/users", headers=secure_client_headers)["id"]

    # update unexisting attribute (bad request)
    updated_user = {"username": "Alice", "something": 42}
    response = secure_client.put(f"/users/{user_id}", json=updated_user, headers=secure_client_headers)
    assert response.status_code == 400

    # change nothing
    response = secure_client.put(f"/users/{user_id}", json={}, headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()

    # nothing changed so far
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()
    
    # update password
    updated_user = {"password": "12345"}
    response = secure_client.put(f"/users/{user_id}", json=updated_user, headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()
    assert "password" not in data # api will not send passwords around
    
    # change username
    updated_user = {"username": "Alice2"}
    response = secure_client.put(f"/users/{user_id}", json=updated_user, headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == get_base_permissions()

    # change permissions
    updated_user = {"permissions": {"MEMORY": ["READ"]}}
    response = secure_client.put(f"/users/{user_id}", json=updated_user, headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == {"MEMORY": ["READ"]}

    # change username and permissions
    updated_user = {"username": "Alice3", "permissions": {"UPLOAD":["WRITE"]}}
    response = secure_client.put(f"/users/{user_id}", json=updated_user, headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice3"
    assert data["permissions"] == {"UPLOAD":["WRITE"]}

    # get list of users, should be admin, user and Alice3
    response = secure_client.get("/users", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    for d in data:
        check_user_fields(d)
        assert d["username"] in ["user", "Alice3"]
        if d["username"] == "Alice3":
            assert d["permissions"] == {"UPLOAD": ["WRITE"]}
        else:
            assert d["permissions"] == get_base_permissions()


def test_delete_user(secure_client, secure_client_headers):
    # delete unexisting user
    response = secure_client.delete("/users/non_existent_id", headers=secure_client_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(secure_client, "/users", headers=secure_client_headers)["id"]

    # delete user
    response = secure_client.delete(f"/users/{user_id}", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id

    # check that the user is not in the db anymore
    response = secure_client.get(f"/users/{user_id}", headers=secure_client_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # check user is no more in the list of users
    response = secure_client.get("/users", headers=secure_client_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1


# note: using secure secure_client (api key set both for http and ws)
def test_no_access_if_api_keys_active(secure_client, secure_client_headers):
    # create user (forbidden)
    response = secure_client.post(
        "/users",
        json={"username": "Alice", "password": new_user_password},
        headers={"agent_id": agent_id}
    )
    assert response.status_code == 403

    # read users (forbidden)
    response = secure_client.get("/users", headers={"agent_id": agent_id})
    assert response.status_code == 403

    # edit user (forbidden)
    response = secure_client.put(
        "/users/non_existent_id", # it does not exist, but request should be blocked before the check
        json={"username": "Alice"},
        headers={"agent_id": agent_id}
    )
    assert response.status_code == 403

    # check default list giving the correct CCAT_API_KEY
    headers = {"Authorization": f"Bearer {api_key}", "agent_id": agent_id}
    response = secure_client.get("/users", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["username"] == "user"
