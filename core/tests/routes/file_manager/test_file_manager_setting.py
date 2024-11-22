import os
from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.factory.file_manager import FileManagerFactory


def test_get_all_file_manager_settings(secure_client, secure_client_headers, lizard):
    file_manager_schemas = FileManagerFactory(lizard.plugin_manager).get_schemas()
    response = secure_client.get("/file_manager/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(file_manager_schemas)

    for setting in json["settings"]:
        assert setting["name"] in file_manager_schemas.keys()
        assert setting["value"] == {}
        expected_schema = file_manager_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected file manager
    assert json["selected_configuration"] == "LocalFileManagerConfig"


def test_get_file_manager_settings_non_existent(secure_client, secure_client_headers):
    non_existent_filemanager_name = "FileManagerNonExistentConfig"
    response = secure_client.get(
        f"/file_manager/settings/{non_existent_filemanager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_filemanager_name} not supported" in json["detail"]["error"]


def test_get_filemanager_settings(secure_client, secure_client_headers):
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.get(
        f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == file_manager_name
    assert json["value"] == {}
    assert json["scheme"]["fileManagerName"] == file_manager_name
    assert json["scheme"]["type"] == "object"
