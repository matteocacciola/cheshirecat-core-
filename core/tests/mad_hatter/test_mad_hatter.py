import pytest
from inspect import isfunction

from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.decorators.hook import CatHook
from cat.mad_hatter.decorators.tool import CatTool

from tests.utils import create_mock_plugin_zip


def test_instantiation_discovery(mad_hatter_no_plugins: MadHatter):
    # Mad Hatter finds core_plugin
    assert list(mad_hatter_no_plugins.plugins.keys()) == ["core_plugin"]
    assert isinstance(mad_hatter_no_plugins.plugins["core_plugin"], Plugin)
    assert "core_plugin" in mad_hatter_no_plugins.load_active_plugins_from_db()

    # finds hooks
    assert len(mad_hatter_no_plugins.hooks.keys()) > 0
    for hook_name, hooks_list in mad_hatter_no_plugins.hooks.items():
        assert len(hooks_list) == 1  # core plugin implements each hook
        h = hooks_list[0]
        assert isinstance(h, CatHook)
        assert h.plugin_id == "core_plugin"
        assert isinstance(h.name, str)
        assert isfunction(h.function)
        assert h.priority == 0.0

    # finds tool
    assert len(mad_hatter_no_plugins.tools) == 1
    tool = mad_hatter_no_plugins.tools[0]
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
    active_plugins = mad_hatter_no_plugins.load_active_plugins_from_db()
    assert len(active_plugins) == 1
    assert active_plugins[0] == "core_plugin"


# installation tests will be run for both flat and nested plugin
@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_install(mad_hatter_no_plugins: MadHatter, plugin_is_flat):
    with pytest.raises(NotImplementedError):
        # install plugin
        new_plugin_zip_path = create_mock_plugin_zip(flat=plugin_is_flat)
        mad_hatter_no_plugins.install_plugin(new_plugin_zip_path)


@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_uninstall(mad_hatter_no_plugins: MadHatter, plugin_is_flat):
    with pytest.raises(NotImplementedError):
        # uninstall
        mad_hatter_no_plugins.uninstall_plugin("mock_plugin")
