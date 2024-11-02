from abc import ABC, abstractmethod
import os
import inspect
import traceback
from copy import deepcopy
from typing import List, Dict

from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.db.models import Setting
from cat.log import log
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.decorators.hook import CatHook
from cat.mad_hatter.decorators.tool import CatTool
from cat.experimental.form.cat_form import CatForm
import cat.utils as utils


class MadHatter(ABC):
    """
    This is the abstract class that defines the methods that the plugin managers should implement.
    """

    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}  # plugins dictionary

        self.hooks: Dict[
            str, List[CatHook]
        ] = {}  # dict of active plugins hooks ( hook_name -> [CatHook, CatHook, ...])
        self.tools: List[CatTool] = []  # list of active plugins tools
        self.forms: List[CatForm] = []  # list of active plugins forms

        self.active_plugins: List[str] = []

        # this callback is set from outside to be notified when plugin sync is completed
        self.on_finish_plugins_sync_callback = lambda: None

        self.find_plugins()

    # Load hooks, tools and forms of the active plugins into the plugin manager
    def _sync_hooks_tools_and_forms(self):
        # emptying tools, hooks and forms
        self.hooks = {}
        self.tools = []
        self.forms = []

        for plugin in self.plugins.values():
            # load hooks, tools and forms from active plugins
            if plugin.id in self.active_plugins:
                # cache tools
                self.tools += plugin.tools

                self.forms += plugin.forms

                # cache hooks (indexed by hook name)
                for h in plugin.hooks:
                    self.hooks.setdefault(h.name, []).append(h)

        # sort each hooks list by priority
        for hook_name in self.hooks.keys():
            self.hooks[hook_name].sort(key=lambda x: x.priority, reverse=True)

        # notify sync has finished (the Lizard will ensure all tools are embedded in vector memory)
        self.on_finish_plugins_sync_callback()

    # check if plugin exists
    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.plugins.keys()

    def load_active_plugins_from_db(self):
        active_plugins = crud_settings.get_setting_by_name(self.agent_key, "active_plugins")
        active_plugins = [] if active_plugins is None else active_plugins["value"]

        # core_plugin is always active
        if "core_plugin" not in active_plugins:
            active_plugins += ["core_plugin"]

        return active_plugins

    def deactivate_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        plugin_is_active = plugin_id in self.active_plugins

        # update list of active plugins, `core_plugin` cannot be deactivated
        if not plugin_is_active or plugin_id == "core_plugin":
            return

        # Deactivate the plugin
        log.warning(f"Toggle plugin {plugin_id}: Deactivate")

        # Execute hook on plugin deactivation
        # Deactivation hook must happen before actual deactivation,
        # otherwise the hook will not be available in _plugin_overrides anymore
        for hook in self.plugins[plugin_id].plugin_overrides:
            if hook.name != "deactivated":
                continue
            hook.function(self.plugins[plugin_id])

        # Remove the plugin from the list of active plugins
        self.active_plugins.remove(plugin_id)

        self.on_plugin_deactivation(plugin_id)
        self._on_finish_toggle_plugin()

    def activate_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        plugin_is_active = plugin_id in self.active_plugins
        if plugin_is_active:
            return

        log.warning(f"Toggle plugin {plugin_id}: Activate")

        self.on_plugin_activation(plugin_id)

        # Execute hook on plugin activation
        # Activation hook must happen before actual activation,
        # otherwise the hook will still not be available in _plugin_overrides
        for hook in self.plugins[plugin_id].plugin_overrides:
            if hook.name == "activated":
                hook.function(self.plugins[plugin_id])

        # Add the plugin in the list of active plugins
        self.active_plugins.append(plugin_id)

        self._on_finish_toggle_plugin()

    def _on_finish_toggle_plugin(self):
        # update DB with list of active plugins, delete duplicate plugins
        active_plugins = list(set(self.active_plugins))
        crud_settings.upsert_setting_by_name(self.agent_key, Setting(name="active_plugins", value=active_plugins))

        # update cache and embeddings
        self._sync_hooks_tools_and_forms()

    # execute requested hook
    def execute_hook(self, hook_name: str, *args, cat):
        # check if hook is supported
        if hook_name not in self.hooks.keys():
            raise Exception(f"Hook {hook_name} not present in any plugin")

        # Hook has no arguments (aside cat)
        #  no need to pipe
        if len(args) == 0:
            for hook in self.hooks[hook_name]:
                try:
                    log.debug(
                        f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
                    )
                    hook.function(cat=cat)
                except Exception as e:
                    log.error(f"Error in plugin {hook.plugin_id}::{hook.name}")
                    log.error(e)
                    plugin_obj = self.plugins[hook.plugin_id]
                    log.warning(plugin_obj.plugin_specific_error_message())
                    traceback.print_exc()
            return

        # Hook with arguments.
        #  First argument is passed to `execute_hook` is the pipeable one.
        #  We call it `tea_cup` as every hook called will receive it as an input,
        #  can add sugar, milk, or whatever, and return it for the next hook
        tea_cup = deepcopy(args[0])

        # run hooks
        for hook in self.hooks[hook_name]:
            try:
                # pass tea_cup to the hooks, along other args
                # hook has at least one argument, and it will be piped
                log.debug(
                    f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
                )
                tea_spoon = hook.function(
                    deepcopy(tea_cup), *deepcopy(args[1:]), cat=cat
                )
                # log.debug(f"Hook {hook.plugin_id}::{hook.name} returned {tea_spoon}")
                if tea_spoon is not None:
                    tea_cup = tea_spoon
            except Exception as e:
                log.error(f"Error in plugin {hook.plugin_id}::{hook.name}")
                log.error(e)
                plugin_obj = self.plugins[hook.plugin_id]
                log.warning(plugin_obj.plugin_specific_error_message())
                traceback.print_exc()

        # tea_cup has passed through all hooks. Return final output
        return tea_cup

    # get plugin object (used from within a plugin)
    # TODO: should we allow to take directly another plugins' obj?
    def get_plugin(self):
        # who's calling?
        calling_frame = inspect.currentframe().f_back
        # Get the module associated with the frame
        module = inspect.getmodule(calling_frame)
        # Get the absolute and then relative path of the calling module's file
        abs_path = inspect.getabsfile(module)
        rel_path = os.path.relpath(abs_path)

        # throw exception if this method is called from outside the plugins folder
        if not rel_path.startswith(utils.get_plugins_path()):
            raise Exception("get_plugin() can only be called from within a plugin")

        # Replace the root and get only the current plugin folder
        plugin_suffix = rel_path.replace(utils.get_plugins_path(), "")
        # Plugin's folder
        name = plugin_suffix.split("/")[0]
        return self.plugins[name]

    @property
    def procedures(self):
        return self.tools + self.forms

    @abstractmethod
    def find_plugins(self):
        pass

    @abstractmethod
    def on_plugin_activation(self, plugin_id: str):
        pass

    @abstractmethod
    def on_plugin_deactivation(self, plugin_id: str):
        pass

    @property
    @abstractmethod
    def agent_key(self):
        pass
