import os

from cat.db import crud
from cat.db.cruds import plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY

from tests.utils import api_key, create_mock_plugin_zip, agent_id, mock_plugin_settings_file


# NOTE: here we test zip upload and install
# installation from registry is in `./test_plugins_registry.py`
def test_plugin_install_from_zip(secure_client, secure_client_headers, just_installed_plugin, cheshire_cat):
    # during tests, the cat uses a different folder for plugins
    mock_plugin_final_folder = "tests/mocks/mock_plugin_folder/mock_plugin"

    #### PLUGIN IS ALREADY ACTIVE

    # GET plugin endpoint responds
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["data"]["id"] == "mock_plugin"
    assert isinstance(json["data"]["active"], bool)
    assert json["data"]["active"]

    # GET plugins endpoint lists the plugin
    response = secure_client.get("/admins/plugins", headers=secure_client_headers)
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" in installed_plugins_names
    # both core_plugin and mock_plugin are active
    for p in installed_plugins:
        assert isinstance(p["active"], bool)
        assert p["active"]

    # now, lists the plugins as an agent (new plugins are deactivated, initially)
    response = secure_client.get(
        "/plugins", headers={"agent_id": cheshire_cat.id, "Authorization": f"Bearer {api_key}"}
    )
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" in installed_plugins_names
    # core_plugin is active, mock_plugin is not at an agent level
    for p in installed_plugins:
        assert isinstance(p["active"], bool)
        assert p["active"] if p["id"] == "core_plugin" else not p["active"]

    # plugin has been actually extracted in (mock) plugins folder
    assert os.path.exists(mock_plugin_final_folder)

    # GET single plugin info, plugin is active
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert isinstance(response.json()["data"]["active"], bool)
    assert response.json()["data"]["active"]


def test_plugin_install_after_cheshire_cat_creation(lizard, secure_client, secure_client_headers):
    # create a new agent
    ccat = lizard.get_cheshire_cat("agent_test_test")

    # list the plugins as an agent (new plugins are deactivated, initially): mock_plugin is not installed
    response = secure_client.get(
        "/plugins", headers={"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}
    )
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" not in installed_plugins_names

    # now, manually install the plugin
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder

    # upload plugin via endpoint
    with open(zip_path, "rb") as f:
        response = secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # request was processed
    assert response.status_code == 200
    assert response.json()["filename"] == zip_file_name

    # now, lists the plugins as an agent (new plugins are deactivated, initially)
    response = secure_client.get(
        "/plugins", headers={"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}
    )
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" in installed_plugins_names
    # core_plugin is active, mock_plugin is not at an agent level
    for p in installed_plugins:
        assert isinstance(p["active"], bool)
        assert p["active"] if p["id"] == "core_plugin" else not p["active"]


def test_plugin_uninstall(secure_client, secure_client_headers, just_installed_plugin):
    # The plugin is active, now let's activate for the agent too
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)
    agent_settings = crud.read(crud_plugins.format_key(agent_id, "mock_plugin"))
    system_settings = crud.read(crud_plugins.format_key(DEFAULT_SYSTEM_KEY, "mock_plugin"))

    assert agent_settings is not None
    assert system_settings is not None

    # during tests, the cat uses a different folder for plugins
    mock_plugin_final_folder = "tests/mocks/mock_plugin_folder/mock_plugin"

    # remove plugin via endpoint (will delete also plugin folder in mock_plugin_folder)
    response = secure_client.delete("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.status_code == 200

    # mock_plugin is not installed in the cat (check both via endpoint and filesystem)
    response = secure_client.get("/admins/plugins", headers=secure_client_headers)
    installed_plugins_names = list(map(lambda p: p["id"], response.json()["installed"]))
    assert "mock_plugin" not in installed_plugins_names
    assert not os.path.exists(mock_plugin_final_folder)  # plugin folder removed from disk

    # GET single plugin info, plugin is not active
    response = secure_client.get("/admins/plugins/mock_plugin", headers=secure_client_headers)
    assert response.json()["detail"]["error"] == "Plugin not found"

    agent_settings = crud.read(crud_plugins.format_key(agent_id, "mock_plugin"))
    system_settings = crud.read(crud_plugins.format_key(DEFAULT_SYSTEM_KEY, "mock_plugin"))

    assert agent_settings is None
    assert system_settings is None


def test_plugin_recurrent_installs(lizard, secure_client, secure_client_headers):
    # create a new agent
    ccat = lizard.get_cheshire_cat("agent_test_test")
    ccat_headers = {"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}

    # manually install the plugin
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # activate for the new agent
    secure_client.put("/plugins/toggle/mock_plugin", headers=ccat_headers)

    # re-install the plugin
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # now, re-list the plugins as an agent: all the plugins should be still active
    response = secure_client.get("/plugins", headers=ccat_headers)
    installed_plugins = response.json()["installed"]
    installed_plugins_names = list(map(lambda p: p["id"], installed_plugins))
    assert "mock_plugin" in installed_plugins_names
    for p in installed_plugins:
        assert isinstance(p["active"], bool)
        assert p["active"]


def test_plugin_incremental_settings_on_recurrent_installs(lizard, secure_client, secure_client_headers):
    # create a new agent
    ccat = lizard.get_cheshire_cat("agent_test_test")
    ccat_headers = {"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}

    # manually install the plugin
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # activate for the new agent
    secure_client.put("/plugins/toggle/mock_plugin", headers=ccat_headers)

    # manually change the configuration of `mock_plugin` for the agent in the Redis database (mock a first update with
    # new keys in the settings)
    agent_settings = crud_plugins.get_setting(ccat.id, "mock_plugin")
    agent_settings["key_a"] = "value_a"
    agent_settings["existing_key"] = "value"
    crud_plugins.update_setting(ccat.id, "mock_plugin", agent_settings)

    # now, write a `settings.py` into the plugin folder and re-install the plugin, so emulating a second
    # update, with a new value in the `existing_key` and the removal of `key_a` in the settings
    mock_plugin_settings_file()
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # check that the configuration of `mock_plugin` for the agent has changed according to the new settings.py
    agent_settings = crud_plugins.get_setting(ccat.id, "mock_plugin")
    assert "key_a" not in agent_settings
    assert agent_settings["existing_key"] == "value"
