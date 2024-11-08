import os
import pytest

from cat.env import get_env

from tests.conftest import api_key, api_key_ws
from tests.utils import send_websocket_message


# utility to make http requests with some headers
def http_request(client, headers=None):
    response = client.post("/message", headers=headers, json={"text": "hey"})
    return response.status_code, response.json()


def set_api_key(key: str, value: str) -> str | None:
    current_api_key = get_env(key)
    # set CCAT_API_KEY
    os.environ[key] = value

    return current_api_key


def reset_api_key(key, value: str | None) -> None:
    # remove CCAT_API_KEY
    if value:
        os.environ[key] = value
    else:
        del os.environ[key]


@pytest.mark.parametrize("header_name", ["Authorization", "access_token"])
def test_api_key_http(secure_client, header_name):
    old_api_key = set_api_key("CCAT_API_KEY", api_key)

    # add "Bearer: " when using `Authorization` header
    key_prefix = ""
    if header_name == "Authorization":
        key_prefix = "Bearer "

    wrong_headers = [
        {}, # no key
        {header_name: f"{key_prefix}wrong"}, # wrong key
        {header_name: f"{key_prefix}{api_key_ws}"}, # websocket key
    ]

    # all the previous headers result in a 403
    for headers in wrong_headers:
        status_code, json = http_request(secure_client, headers)
        assert status_code == 403
        assert json["detail"]["error"] == "Invalid Credentials"

    # allow access if CCAT_API_KEY is right
    headers = {header_name: f"{key_prefix}{api_key}"}
    status_code, json = http_request(secure_client, headers)
    assert status_code == 200

    # allow websocket access without any key
    mex = {"text": "Where do I go?"}
    res = send_websocket_message(mex, secure_client, {"apikey": api_key_ws})
    assert "You did not configure" in res["content"]

    reset_api_key("CCAT_API_KEY", old_api_key)


def test_api_key_ws(secure_client, secure_client_headers):
    # set CCAT_API_KEY_WS
    old_api_key = set_api_key("CCAT_API_KEY_WS", api_key_ws)

    mex = {"text": "Where do I go?"}

    wrong_query_params = [
        {}, # no key
        {"apikey": "wrong"}, # wrong apikey
        {"token": "wrong"}, # wrong token
    ]

    for params in wrong_query_params:
        with pytest.raises(Exception) as e_info:
            send_websocket_message(mex, secure_client, query_params=params)
        assert str(e_info.type.__name__) == "WebSocketDisconnect"

    # allow access if CCAT_API_KEY_WS is right
    query_params = {"apikey": api_key_ws}
    res = send_websocket_message(mex, secure_client, query_params=query_params)
    assert "You did not configure" in res["content"]

    reset_api_key("CCAT_API_KEY_WS", old_api_key)
