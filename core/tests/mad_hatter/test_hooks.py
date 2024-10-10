from cat.mad_hatter.decorators.hook import CatHook
from cat.convo.messages import CatMessage


def test_hook_discovery(mad_hatter):
    mock_plugin_hooks = mad_hatter.plugins["mock_plugin"].hooks

    assert len(mock_plugin_hooks) == 3
    for h in mock_plugin_hooks:
        assert isinstance(h, CatHook)
        assert h.plugin_id == "mock_plugin"


def test_hook_priority_execution(mad_hatter):
    fake_message = CatMessage(content="Priorities:", user_id="Alice")

    out = mad_hatter.execute_hook("before_cat_sends_message", fake_message, cat=None)
    assert out.content == "Priorities: priority 3 priority 2"
