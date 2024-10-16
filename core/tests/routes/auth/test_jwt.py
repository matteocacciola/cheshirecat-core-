import os
import pytest
import time
import jwt

from cat.db.cruds import users as crud_users
from cat.env import get_env
from cat.auth.permissions import AuthPermission, AuthResource
from cat.auth.auth_utils import is_jwt

from tests.utils import send_websocket_message

# TODOAUTH: test token refresh / invalidation / logoff


def test_is_jwt(client, cheshire_cat):
    assert not is_jwt("not_a_jwt.not_a_jwt.not_a_jwt")

    actual_jwt = jwt.encode(
        {"username": "Alice"},
        "some_secret",
        algorithm=get_env("CCAT_JWT_ALGORITHM"),
    )
    assert is_jwt(actual_jwt)


def test_refuse_issue_jwt(client, cheshire_cat):
    agent_id = cheshire_cat.id

    creds = {"username": "user", "password": "wrong"}
    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})

    # wrong credentials
    assert res.status_code == 403
    json = res.json()
    assert json["detail"]["error"] == "Invalid Credentials"


@pytest.mark.asyncio  # to test async functions
async def test_issue_jwt(client, lizard, cheshire_cat):
    agent_id = cheshire_cat.id

    creds = {"username": "user", "password": "user"}

    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 200

    res_json = res.json()

    # did we obtain a JWT?
    assert res_json["token_type"] == "bearer"
    received_token = res_json["access_token"]
    assert is_jwt(received_token)

    # is the JWT correct for core auth handler?
    auth_handler = lizard.core_auth_handler
    user_info = await auth_handler.authorize_user_from_jwt(
        received_token, AuthResource.STATUS, AuthPermission.READ, key_id=agent_id
    )
    assert len(user_info.id) == 36 and len(user_info.id.split("-")) == 5  # uuid4
    assert user_info.name == "user"

    # manual JWT verification
    try:
        payload = jwt.decode(
            received_token,
            get_env("CCAT_JWT_SECRET"),
            algorithms=[get_env("CCAT_JWT_ALGORITHM")],
        )
        assert payload["username"] == "user"
        assert (payload["exp"] - time.time() < 60 * 60 * 24)  # expires in less than 24 hours
    except jwt.exceptions.DecodeError:
        assert False


@pytest.mark.asyncio
async def test_issue_jwt_for_new_user(client, cheshire_cat):
    # create new user
    creds = {"username": "Alice", "password": "Alice"}

    agent_id = cheshire_cat.id

    # we should not obtain a JWT for this user
    # because it does not exist
    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "Invalid Credentials"

    # let's create the user
    res = client.post("/users", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 200

    # now we should get a JWT
    res = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 200

    res_json = res.json()

    # did we obtain a JWT?
    assert res_json["token_type"] == "bearer"
    received_token = res_json["access_token"]
    assert is_jwt(received_token)


# test token expiration after successful login
# NOTE: here we are using the secure_client fixture (see conftest.py)
def test_jwt_expiration(secure_client, cheshire_cat):
    # set ultrashort JWT expiration time
    current_jwt_expire_minutes = os.getenv("CCAT_JWT_EXPIRE_MINUTES")
    os.environ["CCAT_JWT_EXPIRE_MINUTES"] = "0.05"  # 3 seconds

    agent_id = cheshire_cat.id

    # not allowed
    response = secure_client.get("/", headers={"agent_id": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Credentials"

    # request JWT
    creds = {"username": "user", "password": "user"}
    res = secure_client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 200
    token = res.json()["access_token"]

    # allowed via JWT
    headers = {"Authorization": f"Bearer {token}", "agent_id": agent_id}
    response = secure_client.get("/", headers=headers)
    assert response.status_code == 200

    # wait for expiration time
    time.sleep(3)

    # not allowed because JWT expired
    headers = {"Authorization": f"Bearer {token}", "agent_id": agent_id}
    response = secure_client.get("/", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Credentials"

    # restore default env
    if current_jwt_expire_minutes:
        os.environ["CCAT_JWT_EXPIRE_MINUTES"] = current_jwt_expire_minutes
    else:
        del os.environ["CCAT_JWT_EXPIRE_MINUTES"]


# test ws and http endpoints can get user_id from JWT
# NOTE: here we are using the secure_client fixture (see conftest.py)
def test_jwt_imposes_user_id(secure_client, cheshire_cat):
    agent_id = cheshire_cat.id

    # not allowed
    response = secure_client.get("/", headers={"agent_id": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "Invalid Credentials"

    # request JWT
    creds = {"username": "user", "password": "user"}
    res = secure_client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    assert res.status_code == 200
    token = res.json()["access_token"]

    # we will send this message both via http and ws, having the user_id carried by the JWT
    message = {"text": "hey"}

    # send user specific message via http
    headers = {"Authorization": f"Bearer {token}"}
    params = {"agent_id": agent_id}
    response = secure_client.post("/message", headers=headers, json=message, params=params)
    json = response.json()
    assert response.status_code == 200
    assert json["agent_id"] == agent_id

    # send user specific request via ws
    query_params = {"token": token}
    send_websocket_message(message, secure_client, agent_id=agent_id, query_params=query_params)

    # we now recall episodic memories from the user, there should be two of them, both by admin
    params = {"text": "hey", "agent_id": agent_id}
    response = secure_client.get("/memory/recall/", headers=headers, params=params)
    json = response.json()
    assert response.status_code == 200
    episodic_memories = json["vectors"]["collections"]["episodic"]
    assert len(episodic_memories) == 2
    user_db = crud_users.get_user_by_username(agent_id, creds["username"])
    for em in episodic_memories:
        assert em["metadata"]["source"] == user_db["id"]
        assert em["page_content"] == "hey"


# test that a JWT signed knowing the secret, passes
def test_jwt_self_signature_passes_on_unsecure_client(client, cheshire_cat):
    agent_id = cheshire_cat.id

    # get list of users (we need the ids)
    response = client.get("/users", headers={"agent_id": agent_id})
    users = response.json()

    for user in users:
        # create a self signed JWT using the default secret
        token = jwt.encode(
            {"sub": user["id"], "username": user["username"]},
            "secret",
            algorithm=get_env("CCAT_JWT_ALGORITHM"),
        )

        message = {"text": "hey"}

        headers = {"Authorization": f"Bearer {token}", "agent_id": agent_id}
        response = client.post("/message", headers=headers, json=message)
        assert response.status_code == 200
        assert "You did not configure" in response.json()["content"]

        params = {"token": token}
        response = send_websocket_message(message, client, query_params=params, agent_id=agent_id)
        assert "You did not configure" in response["content"]


# test that a JWT signed with the wrong secret is not accepted
def test_jwt_self_signature_fails_on_secure_client(secure_client, cheshire_cat):
    agent_id = cheshire_cat.id

    # get list of users (we need the ids)
    response = secure_client.get(
        "/users",
        headers={
            "Authorization": "Bearer meow_http",
            "agent_id": agent_id,
        })
    users = response.json()

    for user in users:
        # create a self signed JWT using the default secret
        token = jwt.encode(
            {"sub": user["id"], "username": user["username"]},
            "secret",
            algorithm=get_env("CCAT_JWT_ALGORITHM"),
        )

        message = {"text": "hey"}

        # not allowed because CCAT_JWT_SECRET for secure_client is `meow_jwt`
        headers = {"Authorization": f"Bearer {token}", "agent_id": agent_id}
        response = secure_client.post("/message", headers=headers, json=message)
        assert response.status_code == 403

        # not allowed because CCAT_JWT_SECRET for secure_client is `meow_jwt`
        params = {"token": token}
        with pytest.raises(Exception) as e_info:
            send_websocket_message(message, secure_client, query_params=params, agent_id=agent_id)
            assert str(e_info.type.__name__) == "WebSocketDisconnect"
