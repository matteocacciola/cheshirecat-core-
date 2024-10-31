import pytest
from inspect import isfunction

from cat.mad_hatter.decorators.hook import CatHook
from cat.mad_hatter.decorators.tool import CatTool
from cat.mad_hatter.plugin import Plugin

from tests.utils import create_mock_plugin_zip


def test_instantiation_discovery(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager
    
    # Mad Hatter finds core_plugin
    assert list(plugin_manager.plugins.keys()) == ["core_plugin"]
    assert isinstance(plugin_manager.plugins["core_plugin"], Plugin)
    assert "core_plugin" in plugin_manager.load_active_plugins_from_db()

    # finds hooks
    assert len(plugin_manager.hooks.keys()) > 0
    for hook_name, hooks_list in plugin_manager.hooks.items():
        assert len(hooks_list) == 1  # core plugin implements each hook
        h = hooks_list[0]
        assert isinstance(h, CatHook)
        assert h.plugin_id == "core_plugin"
        assert isinstance(h.name, str)
        assert isfunction(h.function)
        assert h.priority == 0.0

    # finds tool
    assert len(plugin_manager.tools) == 1
    tool = plugin_manager.tools[0]
    assert isinstance(tool, CatTool)
    assert tool.plugin_id == "core_plugin"
    assert tool.name == "get_the_time"
    assert (
        tool.description
        == "Useful to get the current time when asked. Input is always None."
    )
    assert isfunction(tool.func)
    assert not tool.return_direct
    assert len(tool.start_examples) == 2
    assert "what time is it" in tool.start_examples
    assert "get the time" in tool.start_examples

    # list of active plugins in DB is correct
    active_plugins = plugin_manager.load_active_plugins_from_db()
    assert len(active_plugins) == 1
    assert active_plugins[0] == "core_plugin"


# installation tests will be run for both flat and nested plugin
@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_install(cheshire_cat, plugin_is_flat):
    plugin_manager = cheshire_cat.plugin_manager

    with pytest.raises(NotImplementedError):
        # install plugin
        new_plugin_zip_path = create_mock_plugin_zip(flat=plugin_is_flat)
        plugin_manager.install_plugin(new_plugin_zip_path)


@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_uninstall(cheshire_cat, plugin_is_flat):
    plugin_manager = cheshire_cat.plugin_manager

    with pytest.raises(NotImplementedError):
        # uninstall
        plugin_manager.uninstall_plugin("mock_plugin")
