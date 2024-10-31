import uuid
import pytest

from cat.auth.auth_utils import hash_password
from cat.auth.permissions import get_full_admin_permissions
from cat.db import models
from cat.db.cruds import settings as crud_settings, users as crud_users
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.factory.auth_handler import AuthHandlerFactory

from tests.utils import agent_id


def test_get_settings(cheshire_cat):
    values = crud_settings.get_settings(DEFAULT_SYSTEM_KEY, "user")
    assert isinstance(values, list)
    assert len(values) == 0

    values = crud_settings.get_settings(agent_id, "user")
    assert isinstance(values, list)
    assert len(values) == 0

    values = crud_settings.get_settings(agent_id, "CoreOnlyAuthConfi")
    assert isinstance(values, list)
    assert len(values) == 1

    crud_settings.create_setting(agent_id, models.Setting(**{
        "name": "CoreOnlyAuthConfig2",
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": "96f4c9d4-b58d-41c5-88e2-c87b94fe012c",
        "updated_at": 1729169367
    }))
    values = crud_settings.get_settings(agent_id, "CoreOnlyAuthConfi")
    assert isinstance(values, list)
    assert len(values) == 2


def test_get_setting_by_category(cheshire_cat):
    factory = AuthHandlerFactory(cheshire_cat.plugin_manager)

    value = crud_settings.get_settings_by_category(agent_id, "")
    assert isinstance(value, list)
    assert len(value) == 0

    value = crud_settings.get_settings_by_category(agent_id, None)
    assert isinstance(value, list)
    assert len(value) == 0

    value = crud_settings.get_settings_by_category(agent_id, factory.setting_factory_category)
    assert isinstance(value, list)
    assert len(value) == 1

    value = crud_settings.get_settings_by_category(agent_id, factory.setting_category)
    assert isinstance(value, list)
    assert len(value) == 1


def test_get_setting_by_name(cheshire_cat):
    value = crud_settings.get_setting_by_name(agent_id, AuthHandlerFactory(cheshire_cat.plugin_manager).setting_name)
    assert isinstance(value, dict)
    assert value["value"]["name"] == "CoreOnlyAuthConfig"


def test_get_setting_by_id(cheshire_cat):
    setting_id = "96f4c9d4-b58d-41c5-88e2-c87b94fe012c"
    expected = {
        "name": "CoreOnlyAuthConfig2",
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": setting_id,
        "updated_at": 1729169367
    }

    crud_settings.create_setting(agent_id, models.Setting(**expected))

    value = crud_settings.get_setting_by_id(agent_id, setting_id)
    assert isinstance(value, dict)
    assert value == expected


def test_delete_setting_by_id(cheshire_cat):
    setting_id = "96f4c9d4-b58d-41c5-88e2-c87b94fe012c"
    add = {
        "name": "CoreOnlyAuthConfig2",
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": setting_id,
        "updated_at": 1729169367
    }

    crud_settings.create_setting(agent_id, models.Setting(**add))
    crud_settings.delete_setting_by_id(agent_id, setting_id)

    value = crud_settings.get_setting_by_id(agent_id, setting_id)

    assert value is None


def test_delete_settings_by_category(cheshire_cat):
    category = AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category
    value = crud_settings.get_settings_by_category(agent_id, category)
    assert len(value) == 1

    crud_settings.delete_settings_by_category(agent_id, category)
    value = crud_settings.get_settings_by_category(agent_id, category)
    assert len(value) == 0


def test_create_setting_with_empty_name(cheshire_cat):
    add = {
        "name": "",
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": "96f4c9d4-b58d-41c5-88e2-c87b94fe012c",
        "updated_at": 1729169367
    }

    with pytest.raises(Exception) as e:
        crud_settings.create_setting(agent_id, models.Setting(**add))


def test_update_setting_by_id(cheshire_cat):
    setting_id = "96f4c9d4-b58d-41c5-88e2-c87b94fe012c"
    add = {
        "name": "CoreOnlyAuthConfig2",
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": setting_id,
        "updated_at": 1729169367
    }

    crud_settings.create_setting(agent_id, models.Setting(**add))

    expected = add.copy()
    expected["name"] = "CoreOnlyAuthConfig3"
    crud_settings.update_setting_by_id(agent_id, models.Setting(**expected))

    value = crud_settings.get_setting_by_id(agent_id, setting_id)
    assert value == expected


def test_upsert_setting_by_name(cheshire_cat):
    name = "CoreOnlyAuthConfig2"
    add = {
        "name": name,
        "value": {},
        "category": AuthHandlerFactory(cheshire_cat.plugin_manager).setting_factory_category,
        "setting_id": "96f4c9d4-b58d-41c5-88e2-c87b94fe012c",
        "updated_at": 1729169367
    }

    # not existing, new one
    crud_settings.upsert_setting_by_name(agent_id, models.Setting(**add))
    value = crud_settings.get_setting_by_name(agent_id, name)
    assert value == add

    # existing: update
    expected = add.copy()
    new_id = str(uuid.uuid4())
    expected["setting_id"] = new_id
    crud_settings.upsert_setting_by_name(agent_id, models.Setting(**expected))
    value = crud_settings.get_setting_by_name(agent_id, name)
    assert value == expected


def test_get_users(lizard):
    users = crud_users.get_users(lizard.config_key)
    assert users is not {}

    ids = list(users.keys())
    assert len(ids) == 1
    assert users[ids[0]]["id"] == ids[0]
    assert users[ids[0]]["username"] == "admin"


def test_get_user(lizard):
    # admin already exists as username
    user = crud_users.create_user(lizard.config_key, {
        "username": "admin",
        "password": hash_password("admin"),
        "permissions": get_full_admin_permissions()
    })
    assert user is None
    users = crud_users.get_users(lizard.config_key)
    assert len(users) == 1

    # create
    expected_user = {
        "username": "admin2",
        "password": hash_password("admin2"),
        "permissions": get_full_admin_permissions()
    }
    user = crud_users.create_user(lizard.config_key, expected_user)
    assert user["username"] == expected_user["username"]
    assert user["permissions"] == expected_user["permissions"]
    users = list(crud_users.get_users(lizard.config_key).values())
    assert len(users) == 2

    user = crud_users.get_user(lizard.config_key, users[1]["id"])
    assert user["username"] == expected_user["username"]
    assert user["permissions"] == expected_user["permissions"]


def test_get_user_by_username(lizard):
    username = "admin2"

    # create
    expected_user = {
        "username": username,
        "password": hash_password("admin2"),
        "permissions": get_full_admin_permissions()
    }
    crud_users.create_user(lizard.config_key, expected_user)

    user = crud_users.get_user_by_username(lizard.config_key, username)
    assert user["username"] == expected_user["username"]
    assert user["permissions"] == expected_user["permissions"]


def test_update_user(lizard):
    # create
    new_user = {
        "username": "admin2",
        "password": hash_password("admin2"),
        "permissions": get_full_admin_permissions()
    }
    user = crud_users.create_user(lizard.config_key, new_user)

    expected_user = user.copy()
    expected_user["username"] = "admin3"

    crud_users.update_user(lizard.config_key, user["id"], expected_user)
    user = crud_users.get_user_by_username(lizard.config_key, "admin3")

    assert user is not None


def test_delete_user(lizard):
    # create
    new_user = {
        "username": "admin2",
        "password": hash_password("admin2"),
        "permissions": get_full_admin_permissions()
    }
    user = crud_users.create_user(lizard.config_key, new_user)

    crud_users.delete_user(lizard.config_key, user["id"])
    user = crud_users.get_user_by_username(lizard.config_key, "admin2")

    assert user is None


def test_get_user_by_credentials(lizard):
    # create
    new_user = {
        "username": "admin2",
        "password": "admin2",
        "permissions": get_full_admin_permissions()
    }
    crud_users.create_user(lizard.config_key, new_user)

    user = crud_users.get_user_by_credentials(lizard.config_key, new_user["username"], new_user["password"])
    assert user is not None
    assert user["username"] == new_user["username"]
    assert user["permissions"] == new_user["permissions"]
