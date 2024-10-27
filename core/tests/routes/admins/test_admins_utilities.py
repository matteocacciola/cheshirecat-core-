from cat.db.cruds import (
    settings as crud_settings,
    history as crud_history,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.db.database import get_db
from cat.env import get_env
from cat.memory.long_term_memory import LongTermMemory

from tests.utils import create_new_user, get_client_admin_headers, new_user_password


def test_agent_destroy_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent_destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) == 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = get_db().get(crud_users.format_key(cheshire_cat.id))
    assert users is None

    assert cheshire_cat.memory is None


def test_agent_reset_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent_reset", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = crud_users.get_users(cheshire_cat.id)
    assert len(users) == 1


def test_agent_destroy_error_because_of_lack_of_permissions(client, lizard, cheshire_cat):
    # create new admin with wrong permissions
    data = create_new_user(
        client, "/admins", headers=get_client_admin_headers(client), permissions={"EMBEDDER": ["READ"]}
    )

    creds = {"username": data["username"], "password": new_user_password}
    res = client.post("/admins/auth/token", json=creds)
    received_token = res.json()["access_token"]

    response = client.post(
        "/admins/utils/agent_destroy",
        headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 403

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0


def test_agent_destroy_error_because_of_lack_not_existing_agent(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent_destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": "wrong_id"}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": False, "deleted_memories": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0
    assert isinstance(cheshire_cat.memory, LongTermMemory)
    assert len(cheshire_cat.memory.vectors.collections) > 0