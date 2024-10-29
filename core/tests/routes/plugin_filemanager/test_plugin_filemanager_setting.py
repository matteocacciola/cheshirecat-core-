import os
from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.factory.plugin_filemanager import PluginFileManagerFactory
import cat.utils as utils


def test_get_all_plugin_filemanager_settings(secure_client, secure_client_headers, lizard):
    filemanager_schemas = PluginFileManagerFactory(lizard.march_hare).get_schemas()
    response = secure_client.get("/plugin_filemanager/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(filemanager_schemas)

    for setting in json["settings"]:
        assert setting["name"] in filemanager_schemas.keys()
        assert setting["value"] == (
            {"storage_dir": utils.get_plugins_path()} if setting["name"] == "LocalPluginFileManagerConfig" else {}
        )
        expected_schema = filemanager_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected file manager
    assert json["selected_configuration"] == "LocalPluginFileManagerConfig"


def test_get_plugin_filemanager_settings_non_existent(secure_client, secure_client_headers):
    non_existent_filemanager_name = "PluginFileManagerNonExistentConfig"
    response = secure_client.get(
        f"/plugin_filemanager/settings/{non_existent_filemanager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_filemanager_name} not supported" in json["detail"]["error"]


def test_get_filemanager_settings(secure_client, secure_client_headers):
    plugin_filemanager_name = "LocalPluginFileManagerConfig"
    response = secure_client.get(
        f"/plugin_filemanager/settings/{plugin_filemanager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == plugin_filemanager_name
    assert json["value"] == {"storage_dir": utils.get_plugins_path()}  # local file manager
    assert json["scheme"]["pluginFileManagerName"] == plugin_filemanager_name
    assert json["scheme"]["type"] == "object"


def test_upsert_plugin_filemanager_settings(secure_client, secure_client_headers):
    plugins_folder = "tests/mocks/mock_plugin_folder/"

    # set the same Plugin file manager with a different folder name as `storage_dir`
    new_plugin_filemanager = "LocalPluginFileManagerConfig"
    plugin_filemanager_config = {"storage_dir": "tests/mocks/mock_plugin_folder_new/"}
    response = secure_client.put(
        f"/plugin_filemanager/settings/{new_plugin_filemanager}",
        json=plugin_filemanager_config,
        headers=secure_client_headers
    )
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_plugin_filemanager
    assert json["value"]["storage_dir"] == plugin_filemanager_config["storage_dir"]

    # retrieve all embedders settings to check if it was saved in DB
    response = secure_client.get("/plugin_filemanager/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_plugin_filemanager
    saved_config = [c for c in json["settings"] if c["name"] == new_plugin_filemanager]
    assert saved_config[0]["value"]["storage_dir"] == plugin_filemanager_config["storage_dir"]

    # check also specific embedder endpoint
    response = secure_client.get(
        f"/plugin_filemanager/settings/{new_plugin_filemanager}", headers=secure_client_headers
    )
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_plugin_filemanager
    assert json["value"]["storage_dir"] == plugin_filemanager_config["storage_dir"]
    assert json["scheme"]["pluginFileManagerName"] == new_plugin_filemanager

    # restore the original folder
    os.system(f"cp -r tests/mocks/mock_plugin_folder_new/ {plugins_folder}")
    os.system(f"chown -R 1000:1000 {plugins_folder}")
    os.system(f"chmod g+rwx,u+rwx,o+rx,o-w {plugins_folder}")
