from cat.auth.permissions import get_base_permissions, get_full_permissions
from tests.utils import create_new_user, check_user_fields


def test_create_user(client, cheshire_cat):
    # create user
    data = create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})

    # assertions on user structure
    check_user_fields(data)

    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()


def test_cannot_create_duplicate_user(client, cheshire_cat):
    # create user
    create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})

    # create user with same username
    response = client.post("/users", json={"username": "Alice", "password": "ecilA"}, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Cannot duplicate user"


def test_get_users(client, cheshire_cat):
    # get list of users
    response = client.get("/users", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0 # admin and user

    # create user
    create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})

    # get updated list of users
    response = client.get("/users", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1

    # check users integrity and values
    d = data[0]
    check_user_fields(d)
    assert d["username"] == "Alice"
    assert d["permissions"] == get_base_permissions()


def test_get_user(client, cheshire_cat):
    # get unexisting user
    response = client.get("/users/wrong_user_id", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})["id"]

    # get specific existing user
    response = client.get(f"/users/{user_id}", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()

    # check user integrity and values
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()


def test_update_user(client, cheshire_cat):
    # update unexisting user
    response = client.put("/users/non_existent_id", json={"username": "Red Queen"}, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})["id"]

    # update unexisting attribute (bad request)
    updated_user = {"username": "Alice", "something": 42}
    response = client.put(f"/users/{user_id}", json=updated_user, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 400

    # change nothing
    response = client.put(f"/users/{user_id}", json={}, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()

    # nothing changed so far
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()
    
    # update password
    updated_user = {"password": "12345"}
    response = client.put(f"/users/{user_id}", json=updated_user, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice"
    assert data["permissions"] == get_base_permissions()
    assert "password" not in data # api will not send passwords around
    
    # change username
    updated_user = {"username": "Alice2"}
    response = client.put(f"/users/{user_id}", json=updated_user, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == get_base_permissions()

    # change permissions
    updated_user = {"permissions": {"MEMORY": ["READ"]}}
    response = client.put(f"/users/{user_id}", json=updated_user, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice2"
    assert data["permissions"] == {"MEMORY": ["READ"]}

    # change username and permissions
    updated_user = {"username": "Alice3", "permissions": {"UPLOAD":["WRITE"]}}
    response = client.put(f"/users/{user_id}", json=updated_user, headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    check_user_fields(data)
    assert data["username"] == "Alice3"
    assert data["permissions"] == {"UPLOAD":["WRITE"]}

    # get list of users, should be admin, user and Alice3
    response = client.get("/users", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1

    d = data[0]
    check_user_fields(d)
    assert d["username"] == "Alice3"
    assert d["permissions"] == {"UPLOAD":["WRITE"]}


def test_delete_user(client, cheshire_cat):
    # delete unexisting user
    response = client.delete("/users/non_existent_id", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # create user and obtain id
    user_id = create_new_user(client, "/users", headers={"agent_id": cheshire_cat.id})["id"]

    # delete user
    response = client.delete(f"/users/{user_id}", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == user_id

    # check that the user is not in the db anymore
    response = client.get(f"/users/{user_id}", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "User not found"

    # check user is no more in the list of users
    response = client.get("/users", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 0


# note: using secure client (api key set both for http and ws)
def test_no_access_if_api_keys_active(secure_client, cheshire_cat):
    # create user (forbidden)
    response = secure_client.post(
        "/users",
        json={"username": "Alice", "password": "wandering_in_wonderland"},
        headers={"agent_id": cheshire_cat.id}
    )
    assert response.status_code == 403

    # read users (forbidden)
    response = secure_client.get("/users", headers={"agent_id": cheshire_cat.id})
    assert response.status_code == 403

    # edit user (forbidden)
    response = secure_client.put(
        "/users/non_existent_id", # it does not exist, but request should be blocked before the check
        json={"username": "Alice"},
        headers={"agent_id": cheshire_cat.id}
    )
    assert response.status_code == 403

    # check default list giving the correct CCAT_API_KEY
    headers = {"Authorization": f"Bearer meow_http", "agent_id": cheshire_cat.id}
    response = secure_client.get("/users", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 0
