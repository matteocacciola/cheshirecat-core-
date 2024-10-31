from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.tweedledum import Tweedledum


class Tweedledee(MadHatter):
    """
    Tweedledee is the plugin manager of the various instance of Cheshire Cat. It is responsible for:
    - Activating a plugin at an agent level
    - Deactivating a plugin at an agent level

    Args:
    -----
    config_key: str
        The key to use to store the active plugins in the database settings. Default is DEFAULT_SYSTEM_KEY.
    """

    def __init__(self, agent_key: str):
        self.__agent_key = agent_key

        super().__init__()

    def install_plugin(self, package_plugin: str):
        raise NotImplementedError

    def uninstall_plugin(self, plugin_id):
        raise NotImplementedError

    def find_plugins(self):
        # plugins are already loaded when BillTheLizard is created, since its plugin manager scans the plugins folder
        # then, we just need to grab the plugins from there
        self.plugins = self.system_plugin_manager.plugins.copy()

        self.active_plugins = self.load_active_plugins_from_db()

        log.info("ACTIVE PLUGINS:")
        log.info(self.active_plugins)

        for plugin_id, plugin in self.plugins.items():
            if plugin_id not in self.active_plugins:
                continue

            try:
                plugin.activate_settings(self.agent_key)
            except Exception as e:
                # Couldn't activate the plugin -> Deactivate it
                self.toggle_plugin(plugin_id)
                raise e

        self._sync_hooks_tools_and_forms()

    # activate / deactivate plugin
    def toggle_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        plugin_is_active = plugin_id in self.active_plugins

        # update list of active plugins
        if plugin_is_active:
            log.warning(f"Toggle plugin {plugin_id}: Deactivate")

            self.deactivate_plugin(plugin_id)
            self.plugins[plugin_id].deactivate_settings(self.agent_key)
        else:
            log.warning(f"Toggle plugin {plugin_id}: Activate")

            # Activate the plugin
            self.plugins[plugin_id].activate_settings(self.agent_key)
            self._activate_plugin(plugin_id)

        self._on_finish_toggle_plugin()

    @property
    def system_plugin_manager(self) -> Tweedledum:
        return Tweedledum()

    @property
    def agent_key(self):
        return self.__agent_key
