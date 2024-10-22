from json import dumps
import pytest
from fastapi.encoders import jsonable_encoder

from cat.factory.auth_handler import AuthHandlerFactory

from tests.utils import api_key, api_key_ws


def test_get_all_auth_handler_settings(secure_client, secure_client_headers, mad_hatter):
    auth_handler_schemas = AuthHandlerFactory(mad_hatter).get_schemas()
    response = secure_client.get("/auth_handler/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(auth_handler_schemas)

    for setting in json["settings"]:
        assert setting["name"] in auth_handler_schemas.keys()
        assert setting["value"] == {}
        expected_schema = auth_handler_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected auth_handler
    assert json["selected_configuration"] == "CoreOnlyAuthConfig"


def test_get_auth_handler_settings_non_existent(secure_client, secure_client_headers):
    non_existent_auth_handler_name = "AuthHandlerNonExistent"
    response = secure_client.get(
        f"/auth_handler/settings/{non_existent_auth_handler_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_auth_handler_name} not supported" in json["detail"]["error"]


@pytest.mark.skip("Have at least another auth_handler class to test")
def test_get_auth_handler_settings(secure_client, secure_client_headers):
    auth_handler_name = "AuthEnvironmentVariablesConfig"
    response = secure_client.get(f"/auth_handler/settings/{auth_handler_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == auth_handler_name
    assert json["value"] == {}
    assert json["scheme"]["authorizatorName"] == auth_handler_name
    assert json["scheme"]["type"] == "object"


@pytest.mark.skip("Have at least another auth_handler class to test")
def test_upsert_auth_handler_settings(secure_client, secure_client_headers):
    # set a different auth_handler from default one (same class different size # TODO: have another fake/test auth_handler class)
    new_auth_handler = "AuthApiKeyConfig"
    auth_handler_config = {
        "api_key_http": api_key,
        "api_key_ws": api_key_ws,
    }
    response = secure_client.put(
        f"/auth_handler/settings/{new_auth_handler}", json=auth_handler_config, headers=secure_client_headers
    )
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_auth_handler

    # Retrieve all auth_handlers settings to check if it was saved in DB

    ## We are now forced to use api_key, otherwise we don't get in
    response = secure_client.get("/auth_handler/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 403
    assert json["detail"]["error"] == "Invalid Credentials"

    ## let's use the configured api_key for http
    response = secure_client.get("/auth_handler/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_auth_handler

    ## check also specific auth_handler endpoint
    response = secure_client.get(f"/auth_handler/settings/{new_auth_handler}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_auth_handler
    assert json["scheme"]["authorizatorName"] == new_auth_handler
