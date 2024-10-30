import os
import pytest
import fnmatch
import subprocess
from inspect import isfunction

from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.mad_hatter.decorators.hook import CatHook
from cat.mad_hatter.decorators.tool import CatTool
from cat.mad_hatter.plugin import Plugin

from tests.conftest import clean_up
from tests.utils import mock_plugin_path, agent_id


def test_create_plugin_wrong_folder():
    with pytest.raises(Exception) as e:
        Plugin("/non/existent/folder")

    assert "Cannot create" in str(e.value)


def test_create_plugin_empty_folder():
    path = "tests/mocks/empty_folder"

    os.mkdir(path)

    with pytest.raises(Exception) as e:
        Plugin(path)

    assert "Cannot create" in str(e.value)


def test_create_plugin(plugin):
    assert not plugin.active

    assert plugin.path == mock_plugin_path
    assert plugin.id == "mock_plugin"

    # manifest
    assert isinstance(plugin.manifest, dict)
    assert plugin.manifest["id"] == plugin.id
    assert plugin.manifest["name"] == "MockPlugin"
    assert "Description not found" in plugin.manifest["description"]

    # hooks and tools
    assert plugin.hooks == []
    assert plugin.tools == []


def test_activate_plugin(plugin):
    # activate it
    plugin.activate(DEFAULT_SYSTEM_KEY)

    assert plugin.active is True

    # hooks
    assert len(plugin.hooks) == 3
    for hook in plugin.hooks:
        assert isinstance(hook, CatHook)
        assert hook.plugin_id == "mock_plugin"
        assert hook.name in [
            "factory_allowed_llms",
            "before_cat_sends_message",
        ]
        assert isfunction(hook.function)

        if hook.name == "before_cat_sends_message":
            assert hook.priority > 1
        else:
            assert hook.priority == 1  # default priority

    # tools
    assert len(plugin.tools) == 1
    tool = plugin.tools[0]
    assert isinstance(tool, CatTool)
    assert tool.plugin_id == "mock_plugin"
    assert tool.name == "mock_tool"
    assert tool.description == "Used to test mock tools. Input is the topic."
    assert isfunction(tool.func)
    assert tool.return_direct is True
    # tool examples found
    assert len(tool.start_examples) == 2
    assert "mock tool example 1" in tool.start_examples
    assert "mock tool example 2" in tool.start_examples


def test_deactivate_plugin(plugin):
    # The plugin is non active by default
    plugin.activate(DEFAULT_SYSTEM_KEY)

    # deactivate it
    plugin.deactivate(DEFAULT_SYSTEM_KEY)

    assert plugin.active is False

    # hooks and tools
    assert len(plugin.hooks) == 0
    assert len(plugin.tools) == 0


def test_settings_schema(plugin):
    settings_schema = plugin.settings_schema()
    assert isinstance(settings_schema, dict)
    assert settings_schema["properties"] == {}
    assert settings_schema["title"] == "PluginSettingsModel"
    assert settings_schema["type"] == "object"


def test_load_settings(plugin):
    settings = plugin.load_settings(DEFAULT_SYSTEM_KEY)
    assert settings == {}


def test_save_settings(plugin):
    fake_settings = {"a": 42}
    plugin.save_settings(fake_settings, DEFAULT_SYSTEM_KEY)

    settings = plugin.load_settings(DEFAULT_SYSTEM_KEY)
    assert settings["a"] == fake_settings["a"]


# Check if plugin requirements have been installed
# ATTENTION: not using `plugin` fixture here, we instantiate and cleanup manually
#           to use the unmocked Plugin class
@pytest.mark.skip_encapsulation
def test_install_plugin_dependencies():
    # manual cleanup
    clean_up()
    # Uninstall mock plugin requirements
    os.system("pip uninstall -y pip-install-test")

    # Install mock plugin
    p = Plugin(mock_plugin_path)

    # Dependencies are installed on plugin activation
    p.activate(DEFAULT_SYSTEM_KEY)

    # pip-install-test should have been installed
    result = subprocess.run(["pip", "list"], stdout=subprocess.PIPE)
    result = result.stdout.decode()
    assert fnmatch.fnmatch(result, "*pip-install-test*")

    # manual cleanup
    clean_up()
    # Uninstall mock plugin requirements
    os.system("pip uninstall -y pip-install-test")
