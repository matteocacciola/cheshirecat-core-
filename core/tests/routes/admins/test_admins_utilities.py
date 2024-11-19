import uuid
from qdrant_client.http.models import Filter, FieldCondition, MatchValue

from cat.db.cruds import (
    settings as crud_settings,
    history as crud_history,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.db.database import get_db
from cat.db.vector_database import get_vector_db
from cat.env import get_env
from cat.memory.long_term_memory import LongTermMemory
from cat.memory.vector_memory_collection import VectorMemoryCollectionTypes

from tests.utils import create_new_user, get_client_admin_headers, new_user_password


def test_factory_reset_success(client, lizard, cheshire_cat):
    # check that the vector database is not empty
    assert len(get_vector_db().get_collections().collections) > 0

    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/factory/reset", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": True}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) == 0

    # check that the Lizard has been correctly recreated from scratch
    settings = crud_settings.get_settings(lizard.config_key)
    assert len(settings) > 0

    # check that the vector database is empty
    assert len(get_vector_db().get_collections().collections) == 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = get_db().get(crud_users.format_key(cheshire_cat.id))
    assert users is None

    assert cheshire_cat.memory is None


def test_agent_destroy_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) == 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = get_db().get(crud_users.format_key(cheshire_cat.id))
    assert users is None

    assert cheshire_cat.memory is None

    qdrant_filter = Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cheshire_cat.id))])
    for c in VectorMemoryCollectionTypes:
        assert get_vector_db().count(collection_name=str(c), count_filter=qdrant_filter).count == 0


def test_agent_reset_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/reset", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = crud_users.get_users(cheshire_cat.id)
    assert len(users) == 1

    ccat = lizard.get_cheshire_cat(cheshire_cat.id)
    for c in VectorMemoryCollectionTypes:
        num_vectors = ccat.memory.vectors.collections[str(c)].get_vectors_count()
        points, _ = ccat.memory.vectors.collections[str(c)].get_all_points()
        assert num_vectors == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1
        assert len(points) == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1


def test_agent_destroy_error_because_of_lack_of_permissions(client, lizard, cheshire_cat):
    # create new admin with wrong permissions
    data = create_new_user(
        client, "/admins/users", headers=get_client_admin_headers(client), permissions={"EMBEDDER": ["READ"]}
    )

    creds = {"username": data["username"], "password": new_user_password}
    res = client.post("/admins/auth/token", json=creds)
    received_token = res.json()["access_token"]

    response = client.post(
        "/admins/utils/agent/destroy",
        headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 403

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0
    assert isinstance(cheshire_cat.memory, LongTermMemory)
    assert len(cheshire_cat.memory.vectors.collections) > 0

    for c in VectorMemoryCollectionTypes:
        num_vectors = cheshire_cat.memory.vectors.collections[str(c)].get_vectors_count()
        points, _ = cheshire_cat.memory.vectors.collections[str(c)].get_all_points()
        assert num_vectors == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1
        assert len(points) == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1


def test_agent_destroy_error_because_of_lack_not_existing_agent(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": "wrong_id"}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": False, "deleted_memories": False, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0
    assert isinstance(cheshire_cat.memory, LongTermMemory)
    assert len(cheshire_cat.memory.vectors.collections) > 0

    for c in VectorMemoryCollectionTypes:
        num_vectors = cheshire_cat.memory.vectors.collections[str(c)].get_vectors_count()
        points, _ = cheshire_cat.memory.vectors.collections[str(c)].get_all_points()
        assert num_vectors == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1
        assert len(points) == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1


def test_agent_create_success(client, lizard):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    new_agent_id = str(uuid.uuid4())

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/create", headers={"Authorization": f"Bearer {received_token}", "agent_id": new_agent_id}
    )

    assert response.status_code == 200
    assert response.json() == {"created": True}

    settings = crud_settings.get_settings(new_agent_id)
    assert len(settings) > 0

    histories = get_db().get(crud_history.format_key(new_agent_id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(new_agent_id, "*"))
    assert plugins is None

    users = crud_users.get_users(new_agent_id)
    assert len(users) == 1

    ccat = lizard.get_cheshire_cat(new_agent_id)
    for c in VectorMemoryCollectionTypes:
        num_vectors = ccat.memory.vectors.collections[str(c)].get_vectors_count()
        points, _ = ccat.memory.vectors.collections[str(c)].get_all_points()
        assert num_vectors == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1
        assert len(points) == 0 if c != VectorMemoryCollectionTypes.PROCEDURAL else 1