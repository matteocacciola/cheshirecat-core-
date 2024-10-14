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

from cat.auth import auth_utils
from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.bill_the_lizard import BillTheLizard
from cat.db.database import Database
from cat.env import get_env
from cat.looking_glass.stray_cat import StrayCat
from cat.mad_hatter.plugin import Plugin
from cat.main import cheshire_cat_api
from cat.memory.vector_memory import VectorMemory
import cat.utils as utils

from tests.utils import create_mock_plugin_zip

mock_plugin_path = "tests/mocks/mock_plugin/"
redis_client = redis.Redis(host=get_env("CCAT_REDIS_HOST"), db="1", encoding="utf-8", decode_responses=True)
agent_id = "agent_test"


# substitute classes' methods where necessary for testing purposes
def mock_classes(monkeypatch):
    # Use in memory vector db
    def mock_connect_to_vector_memory(self, *args, **kwargs):
        return QdrantClient(":memory:")

    monkeypatch.setattr(
        VectorMemory, "connect_to_vector_memory", mock_connect_to_vector_memory
    )

    # Use a different redis client
    def mock_get_redis_client(self, *args, **kwargs):
        return redis_client

    monkeypatch.setattr(Database().__class__, "get_redis_client", mock_get_redis_client)

    # Use mock utils plugin folder
    def get_test_plugin_folder():
        return "tests/mocks/mock_plugin_folder/"

    utils.get_plugins_path = get_test_plugin_folder

    # do not check plugin dependencies at every restart
    def mock_install_requirements(self, *args, **kwargs):
        pass

    monkeypatch.setattr(Plugin, "_install_requirements", mock_install_requirements)

    def get_extract_agent_id_from_request(request):
        return agent_id

    auth_utils.extract_agent_id_from_request = get_extract_agent_id_from_request


# get rid of tmp files and folders used for testing
def clean_up_mocks():
    # clean up service files and mocks
    to_be_removed = [
        "tests/mocks/mock_plugin.zip",
        "tests/mocks/mock_plugin/settings.json",
        "tests/mocks/mock_plugin_folder/mock_plugin",
        "tests/mocks/empty_folder",
    ]
    for tbr in to_be_removed:
        if os.path.exists(tbr):
            if os.path.isdir(tbr):
                shutil.rmtree(tbr)
            else:
                os.remove(tbr)

    redis_client.flushdb()


def should_skip_encapsulation(request):
    return request.node.get_closest_marker("skip_encapsulation") is not None


@pytest.fixture(autouse=True)
def encapsulate_each_test(request, monkeypatch):
    if should_skip_encapsulation(request):
        # Skip initialization for tests marked with @pytest.mark.skip_initialization
        yield

        return

    # monkeypatch classes
    mock_classes(monkeypatch)

    # clean up tmp files, folders and redis database
    clean_up_mocks()

    # delete all singletons!!!
    utils.singleton.instances = {}

    yield

    # clean up tmp files, folders and redis database
    clean_up_mocks()


# Main fixture for the FastAPI app
@pytest.fixture(scope="function")
def client(monkeypatch) -> Generator[TestClient, Any, None]:
    """
    Create a new FastAPI TestClient.
    """

    # monkeypatch classes
    mock_classes(monkeypatch)

    # clean up tmp files, folders and redis database
    clean_up_mocks()

    # delete all singletons!!!
    utils.singleton.instances = {}

    with TestClient(cheshire_cat_api) as client:
        yield client


@pytest.fixture(scope="function")
def lizard():
    yield BillTheLizard()


# This fixture sets the CCAT_API_KEY and CCAT_API_KEY_WS environment variables,
# making mandatory for clients to possess api keys or JWT
@pytest.fixture(scope="function")
def secure_client(client):
    current_api_key = os.getenv("CCAT_API_KEY")
    current_api_ws = os.getenv("CCAT_API_KEY_WS")

    # set ENV variables
    os.environ["CCAT_API_KEY"] = "meow_http"
    os.environ["CCAT_API_KEY_WS"] = "meow_ws"

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


# This fixture is useful to write tests in which
#   a plugin was just uploaded via http.
#   It wraps any test function having `just_installed_plugin` as an argument
@pytest.fixture(scope="function")
def just_installed_plugin(client):
    ### executed before each test function

    # create zip file with a plugin
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder

    # upload plugin via endpoint
    with open(zip_path, "rb") as f:
        response = client.post(
            "/plugins/upload/", files={"file": (zip_file_name, f, "application/zip")}
        )

    # request was processed
    assert response.status_code == 200
    assert response.json()["filename"] == zip_file_name

    ### each test function having `just_installed_plugin` as argument, is run here
    yield
    ###

    # clean up of zip file and mock_plugin_folder is done for every test automatically (see client fixture)


@pytest.fixture
def cheshire_cat(client, lizard):
    cheshire_cat = lizard.get_or_create_cheshire_cat(agent_id)
    yield cheshire_cat
    lizard.remove_cheshire_cat(agent_id)


@pytest.fixture
def mad_hatter(client, cheshire_cat):  # client here injects the monkeypatched version of the manager
    # each test is given the mad_hatter instance
    mad_hatter = cheshire_cat.mad_hatter

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    mad_hatter.install_plugin(new_plugin_zip_path)

    yield mad_hatter


@pytest.fixture
def mad_hatter_no_plugins(client, cheshire_cat):  # client here injects the monkeypatched version of the manager
    mad_hatter = cheshire_cat.mad_hatter

    # each test is given the mad_hatter instance
    yield mad_hatter


@pytest.fixture
def mad_hatter_lizard(client, lizard):  # client here injects the monkeypatched version of the manager
    mad_hatter = lizard.mad_hatter

    # each test is given the mad_hatter instance
    yield mad_hatter


# fixtures to test the main agent
@pytest.fixture
def main_agent(client, lizard):
    yield lizard.main_agent  # each test receives as argument the main agent instance


# fixture to have available an instance of StrayCat
@pytest.fixture
def stray(client, cheshire_cat):
    user = AuthUserInfo(id="user_alice", name="Alice", permissions=get_base_permissions())
    stray_cat = StrayCat(user_data=user, main_loop=asyncio.new_event_loop(), agent_id=cheshire_cat.id)
    stray_cat.working_memory.user_message_json = {"user_id": user.id, "text": "meow"}

    cheshire_cat.add_stray(stray_cat)

    yield stray_cat


@pytest.fixture
def stray_no_memory(client, cheshire_cat) -> StrayCat:
    yield StrayCat(
        user_data=AuthUserInfo(id="user_alice", name="Alice", permissions=get_base_permissions()),
        main_loop=asyncio.new_event_loop(),
        agent_id=cheshire_cat.id
    )


# autouse fixture will be applied to *all* the tests
@pytest.fixture(autouse=True)
def apply_warning_filters():
    # ignore deprecation warnings due to langchain not updating to pydantic v2
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)


# this fixture will give test functions a ready instantiated plugin
# (and having the `client` fixture, a clean setup every unit)
@pytest.fixture
def plugin(client, cheshire_cat):
    p = Plugin(mock_plugin_path)
    yield p


# Define the custom marker
pytest.mark.skip_encapsulation = pytest.mark.skip_encapsulation