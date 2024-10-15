import pytest
import time
import jwt

from cat.env import get_env
from cat.auth.permissions import AdminAuthResource, AuthPermission
from cat.auth.auth_utils import is_jwt
from cat.utils import DefaultAgentKeys


def test_is_jwt(client):
    assert not is_jwt("not_a_jwt.not_a_jwt.not_a_jwt")

    actual_jwt = jwt.encode(
        {"username": "Alice"},
        get_env("CCAT_JWT_SECRET"),
        algorithm=get_env("CCAT_JWT_ALGORITHM"),
    )
    assert is_jwt(actual_jwt)


def test_refuse_issue_jwt(client):
    creds = {"username": "admin", "password": "wrong"}
    res = client.post("/admins/token", json=creds)

    # wrong credentials
    assert res.status_code == 403
    json = res.json()
    assert json["detail"]["error"] == "Invalid Credentials"


@pytest.mark.asyncio  # to test async functions
async def test_issue_jwt(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": "admin"
    }

    res = client.post("/admins/token", json=creds)
    assert res.status_code == 200

    res_json = res.json()

    # did we obtain a JWT?
    assert res_json["token_type"] == "bearer"
    received_token = res_json["access_token"]
    assert is_jwt(received_token)

    # is the JWT correct for core auth handler?
    auth_handler = lizard.core_auth_handler
    user_info = await auth_handler.authorize_user_from_jwt(
        received_token, AdminAuthResource.EMBEDDER, AuthPermission.WRITE, str(DefaultAgentKeys.SYSTEM)
    )
    assert len(user_info.id) == 36 and len(user_info.id.split("-")) == 5 # uuid4
    assert user_info.name == "admin"

    # manual JWT verification
    try:
        payload = jwt.decode(
            received_token,
            get_env("CCAT_JWT_SECRET"),
            algorithms=[get_env("CCAT_JWT_ALGORITHM")],
        )
        assert payload["username"] == "admin"
        assert (
            payload["exp"] - time.time() < 60 * 60 * 24
        )  # expires in less than 24 hours
    except jwt.exceptions.DecodeError:
        assert False


@pytest.mark.asyncio
async def test_issue_jwt_for_new_admin(client):
    # create new user
    creds = {
        "username": "Alice",
        "password": "Alice",
    }

    # we should not obtain a JWT for this user
    # because it does not exist
    res = client.post("/admins/token", json=creds)
    assert res.status_code == 403
    assert res.json()["detail"]["error"] == "Invalid Credentials"

    # let's create the user
    res = client.post("/admins", json=creds)
    assert res.status_code == 200

    # now we should get a JWT
    res = client.post("/admins/token", json=creds)
    assert res.status_code == 200

    # did we obtain a JWT?
    received_token = res.json()["access_token"]
    assert is_jwt(received_token)
