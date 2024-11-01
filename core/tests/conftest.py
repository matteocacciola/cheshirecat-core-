import asyncio
import pytest
import os
import shutil
import redis
from typing import Any, Generator
import warnings
from pydantic import PydanticDeprecatedSince20
from qdrant_client import QdrantClient
from fastapi.testclient import TestClient
import time

from cat.auth import auth_utils
from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.bill_the_lizard import BillTheLizard
from cat.convo.messages import UserMessage
from cat.db.database import Database
from cat.db.vector_database import VectorDatabase, LOCAL_FOLDER_PATH
from cat.env import get_env
from cat.looking_glass.stray_cat import StrayCat
from cat.mad_hatter.plugin import Plugin
from cat.startup import cheshire_cat_api
import cat.utils as utils

from tests.utils import (
    agent_id,
    api_key,
    api_key_ws,
    jwt_secret,
    create_mock_plugin_zip,
    get_class_from_decorated_singleton,
    async_run,
    mock_plugin_path,
    fake_timestamp,
)

redis_client = redis.Redis(host=get_env("CCAT_REDIS_HOST"), db="1", encoding="utf-8", decode_responses=True)


# substitute classes' methods where necessary for testing purposes
def mock_classes(monkeypatch):
    # Use in memory vector db
    def mock_connect_to_vector_memory(self, *args, **kwargs):
        return QdrantClient(":memory:")

    monkeypatch.setattr(
        get_class_from_decorated_singleton(VectorDatabase), "connect_to_vector_memory", mock_connect_to_vector_memory
    )

    # Use a different redis client
    def mock_get_redis_client(self, *args, **kwargs):
        return redis_client

    monkeypatch.setattr(get_class_from_decorated_singleton(Database), "get_redis_client", mock_get_redis_client)

    # Use mock utils plugin folder
    def get_test_plugin_folder():
        return "tests/mocks/mock_plugin_folder/"

    utils.get_plugins_path = get_test_plugin_folder

    # do not check plugin dependencies at every restart
    def mock_install_requirements(self, *args, **kwargs):
        pass

    monkeypatch.setattr(Plugin, "_install_requirements", mock_install_requirements)

    # mock the agent_id in the request
    def get_extract_agent_id_from_request(request):
        return agent_id

    auth_utils.extract_agent_id_from_request = get_extract_agent_id_from_request


def clean_up():
    # clean up service files and mocks
    to_be_removed = [
        "tests/mocks/mock_plugin.zip",
        "tests/mocks/mock_plugin/settings.json",
        "tests/mocks/mock_plugin_folder/mock_plugin",
        "tests/mocks/mock_plugin_folder_new/mock_plugin",
        "tests/mocks/empty_folder",
    ]
    for tbr in to_be_removed:
        if os.path.exists(tbr):
            if os.path.isdir(tbr):
                shutil.rmtree(tbr)
            else:
                os.remove(tbr)

    redis_client.flushdb()

    # wait for the flushdb to be completed
    time.sleep(0.1)


# remove the local Qdrant memory
def clean_up_qdrant():
    # remove the local Qdrant memory
    if os.path.exists(LOCAL_FOLDER_PATH):
        shutil.rmtree(LOCAL_FOLDER_PATH)


def should_skip_encapsulation(request):
    return request.node.get_closest_marker("skip_encapsulation") is not None


@pytest.fixture(autouse=True)
def encapsulate_each_test(request, monkeypatch):
    if should_skip_encapsulation(request):
        # Skip initialization for tests marked with @pytest.mark.skip_initialization
        yield

        return

    clean_up_qdrant()

    # monkeypatch classes
    mock_classes(monkeypatch)

    # env variables
    current_ccat_debug = get_env("CCAT_DEBUG")
    os.environ["CCAT_DEBUG"] = "false"  # do not autoreload

    # clean up tmp files, folders and redis database
    clean_up()

    # delete all singletons!!!
    utils.singleton.instances = {}

    yield

    # clean up tmp files, folders and redis database
    clean_up()

    if current_ccat_debug:
        os.environ["CCAT_DEBUG"] = current_ccat_debug

    clean_up_qdrant()


@pytest.fixture(scope="function")
def lizard():
    yield BillTheLizard()


# Main fixture for the FastAPI app
@pytest.fixture(scope="function")
def client(lizard) -> Generator[TestClient, Any, None]:
    """
    Create a new FastAPI TestClient.
    """

    with TestClient(cheshire_cat_api) as client:
        yield client


# This fixture sets the CCAT_API_KEY and CCAT_API_KEY_WS environment variables,
# making mandatory for clients to possess api keys or JWT
@pytest.fixture(scope="function")
def secure_client(client):
    current_api_key = os.getenv("CCAT_API_KEY")
    current_api_ws = os.getenv("CCAT_API_KEY_WS")
    current_jwt_secret = os.getenv("CCAT_JWT_SECRET")

    # set ENV variables
    os.environ["CCAT_API_KEY"] = api_key
    os.environ["CCAT_API_KEY_WS"] = api_key_ws
    os.environ["CCAT_JWT_SECRET"] = jwt_secret

    yield client

    # clean up
    if current_api_key:
        os.environ["CCAT_API_KEY"] = current_api_key
    else:
        del os.environ["CCAT_API_KEY"]
    if current_api_ws:
        os.environ["CCAT_API_KEY_WS"] = current_api_ws
    else:
        del os.environ["CCAT_API_KEY_WS"]
    if current_jwt_secret:
        os.environ["CCAT_JWT_SECRET"] = current_jwt_secret
    else:
        del os.environ["CCAT_JWT_SECRET"]


@pytest.fixture(scope="function")
def secure_client_headers(secure_client):
    yield {"agent_id": agent_id, "Authorization": f"Bearer {api_key}"}


# This fixture is useful to write tests in which
#   a plugin was just uploaded via http.
#   It wraps any test function having `just_installed_plugin` as an argument
@pytest.fixture(scope="function")
def just_installed_plugin(secure_client, secure_client_headers):
    ### executed before each test function

    # create zip file with a plugin
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

    yield

    # clean up of zip file and mock_plugin_folder is done for every test automatically (see client fixture)


@pytest.fixture
def cheshire_cat(lizard):
    cheshire_cat = lizard.get_or_create_cheshire_cat(agent_id)

    yield cheshire_cat

    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_run(loop, lizard.remove_cheshire_cat, agent_id))


@pytest.fixture
def plugin_manager(lizard):
    plugin_manager = lizard.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_manager.install_plugin(new_plugin_zip_path)

    yield plugin_manager


@pytest.fixture
def agent_plugin_manager(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_id = cheshire_cat.lizard.plugin_manager.install_plugin(new_plugin_zip_path)

    # activate the plugin within the Cheshire Cat whose plugin manager is being used
    plugin_manager.toggle_plugin(plugin_id)

    yield plugin_manager


@pytest.fixture
def embedder(lizard):
    yield lizard.embedder


@pytest.fixture
def llm(cheshire_cat):
    yield cheshire_cat.large_language_model


@pytest.fixture
def memory(client, cheshire_cat):
    yield cheshire_cat.memory


@pytest.fixture
def stray_no_memory(client, cheshire_cat, lizard) -> StrayCat:
    stray_cat = StrayCat(
        user_data=AuthUserInfo(id="user_alice", name="Alice", permissions=get_base_permissions()),
        main_loop=asyncio.new_event_loop(),
        agent_id=cheshire_cat.id
    )

    cheshire_cat.add_stray(stray_cat)

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_id = lizard.plugin_manager.install_plugin(new_plugin_zip_path)

    # activate the plugin within the Cheshire Cat whose plugin manager is being used
    cheshire_cat.plugin_manager.toggle_plugin(plugin_id)

    yield stray_cat


# fixture to have available an instance of StrayCat
@pytest.fixture
def stray(stray_no_memory):
    stray_no_memory.working_memory.user_message = UserMessage(
        user_id=stray_no_memory.user.id, text="meow", agent_id=stray_no_memory.agent_id
    )

    yield stray_no_memory


# autouse fixture will be applied to *all* the tests
@pytest.fixture(autouse=True)
def apply_warning_filters():
    # ignore deprecation warnings due to langchain not updating to pydantic v2
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)


#fixture for mock time.time function
@pytest.fixture
def patch_time_now(monkeypatch):
    def mytime():
        return fake_timestamp

    monkeypatch.setattr(time, 'time', mytime)


# this fixture will give test functions a ready instantiated plugin
# (and having the `client` fixture, a clean setup every unit)
@pytest.fixture
def plugin(client):
    p = Plugin(mock_plugin_path)
    yield p


# Define the custom marker
pytest.mark.skip_encapsulation = pytest.mark.skip_encapsulation