import asyncio
from typing import Dict, List
from uuid import uuid4
from langchain_core.embeddings import Embeddings

from cat import utils
from cat.adapters.factory_adapter import FactoryAdapter
from cat.agents.main_agent import MainAgent
from cat.auth.auth_utils import hash_password, DEFAULT_ADMIN_USERNAME
from cat.auth.permissions import get_full_admin_permissions
from cat.db.cruds import users as crud_users, plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.env import get_env
from cat.exceptions import LoadMemoryException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.factory.custom_filemanager import BaseFileManager
from cat.factory.embedder import EmbedderFactory
from cat.factory.plugin_filemanager import PluginFileManagerFactory
from cat.jobs import job_on_idle_strays
from cat.log import log
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.tweedledum import Tweedledum
from cat.memory.vector_memory_collection import VectorEmbedderSize
from cat.rabbit_hole import RabbitHole
from cat.utils import singleton


@singleton
class BillTheLizard:
    """
    Singleton class that manages the Cheshire Cats and their strays.

    The Cheshire Cats are the agents that are currently active and have users to attend.
    The strays are the users that are waiting for an agent to attend them.

    The Bill The Lizard Manager is responsible for:
    - Creating and deleting Cheshire Cats
    - Adding and removing strays from Cheshire Cats
    - Getting the Cheshire Cat of a stray
    - Getting the strays of a Cheshire Cat
    """

    def __init__(self):
        """
        Bill the Lizard initialization.
        At init time the Lizard executes the bootstrap.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the Embedder, the *Main Agent*, the *Rabbit Hole* and
        the *White Rabbit*.
        """

        self.__cheshire_cats: Dict[str, CheshireCat] = {}
        self.__key = DEFAULT_SYSTEM_KEY

        self.embedder: Embeddings | None = None
        self.embedder_name: str | None = None
        self.embedder_size: VectorEmbedderSize | None = None

        self.plugin_filemanager: BaseFileManager | None = None

        # Start scheduling system
        self.white_rabbit = WhiteRabbit()
        self.__check_idle_strays_job_id = self.white_rabbit.schedule_cron_job(
            lambda: job_on_idle_strays(self, asyncio.new_event_loop()), second=int(get_env("CCAT_STRAYCAT_TIMEOUT"))
        )

        self.plugin_manager = Tweedledum()

        # load embedder
        self.load_language_embedder()

        # load plugin file manager
        self.load_plugin_filemanager()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # Main agent instance (for reasoning)
        self.main_agent = MainAgent()

        self.plugin_manager.on_finish_plugin_install_callback = self.notify_plugin_installed
        self.plugin_manager.on_finish_plugin_uninstall_callback = self.clean_up_plugin_uninstall

        # Initialize the default admin if not present
        if not crud_users.get_users(self.__key):
            self.__initialize_users()

    def notify_plugin_installed(self):
        """
        Notify the loaded Cheshire cats that a plugin was installed, thus reloading the available plugins into the
        cats.
        """

        for ccat in self.__cheshire_cats.values():
            # inform the Cheshire Cats about the new plugin available in the system
            ccat.plugin_manager.find_plugins()

    def clean_up_plugin_uninstall(self, plugin_id: str):
        """
        Clean up the plugin uninstallation. It removes the plugin settings from the database.

        Args:
            plugin_id: The id of the plugin to remove
        """

        for ccat in self.__cheshire_cats.values():
            # deactivate plugins in the Cheshire Cats
            ccat.plugin_manager.deactivate_plugin(plugin_id)
            ccat.plugin_manager.reload_plugins()

        # remove all plugin settings, regardless for system or whatever agent
        crud_plugins.destroy_plugin(plugin_id)

    def __initialize_users(self):
        admin_id = str(uuid4())

        crud_users.set_users(self.__key, {
            admin_id: {
                "id": admin_id,
                "username": DEFAULT_ADMIN_USERNAME,
                "password": hash_password(get_env("CCAT_ADMIN_DEFAULT_PASSWORD")),
                # admin has all permissions
                "permissions": get_full_admin_permissions()
            }
        })

    def load_language_embedder(self):
        """
        Hook into the embedder selection. Allows to modify how the Lizard selects the embedder at bootstrap time.
        """

        factory = EmbedderFactory(self.plugin_manager)

        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.__key)

        self.embedder = factory.get_from_config_name(self.__key, selected_config["value"]["name"])

        self.embedder_name = "default_embedder"
        if hasattr(self.embedder, "model"):
            self.embedder_name = self.embedder.model
        if hasattr(self.embedder, "repo_id"):
            self.embedder_name = self.embedder.repo_id

        # Get embedder size (langchain classes do not store it)
        embedder_size = len(self.embedder.embed_query("hello world"))
        self.embedder_size = VectorEmbedderSize(text=embedder_size)


    def load_plugin_filemanager(self):
        """
        Hook into the plugin file manager selection. Allows to modify how the Lizard selects the plugin file manager at
        bootstrap time.
        """

        factory = PluginFileManagerFactory(self.plugin_manager)

        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.__key)

        self.plugin_filemanager = factory.get_from_config_name(self.__key, selected_config["value"]["name"])

    def replace_embedder(self, language_embedder_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current embedder with a new one. This method is used to change the embedder of the lizard.

        Args:
            language_embedder_name: name of the new embedder
            settings: settings of the new embedder

        Returns:
            The dictionary resuming the new name and settings of the embedder
        """

        adapter = FactoryAdapter(EmbedderFactory(self.plugin_manager))
        updater = adapter.upsert_factory_config_by_settings(self.__key, language_embedder_name, settings)

        # reload the embedder of the lizard
        self.load_language_embedder()

        for ccat in self.__cheshire_cats.values():
            try:
                # create new collections (different embedder!)
                ccat.load_memory()
            except Exception as e:  # restore the original Embedder
                log.error(e)

                # something went wrong: rollback
                adapter.rollback_factory_config(self.__key)

                if updater.old_setting is not None:
                    self.replace_embedder(updater.old_setting["value"]["name"], updater.old_factory["value"])

                raise LoadMemoryException(f"Load memory exception: {utils.explicit_error_message(e)}")

        # recreate tools embeddings
        self.plugin_manager.find_plugins()

        return ReplacedNLPConfig(name=language_embedder_name, value=updater.new_setting["value"])

    def replace_plugin_filemanager(self, plugin_filemanager_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current plugin file manager with a new one. This method is used to change the plugin file manager of
        the lizard.

        Args:
            plugin_filemanager_name: name of the new plugin file manager
            settings: settings of the new plugin file manager

        Returns:
            The dictionary resuming the new name and settings of the plugin file manager
        """

        adapter = FactoryAdapter(PluginFileManagerFactory(self.plugin_manager))
        updater = adapter.upsert_factory_config_by_settings(self.__key, plugin_filemanager_name, settings)

        try:
            old_filemanager = self.plugin_filemanager

            # reload the plugin file manager of the lizard
            self.load_plugin_filemanager()

            self.plugin_filemanager.transfer(old_filemanager)
        except ValueError as e:
            log.error(f"Error while loading the new Plugin File Manager: {e}")

            # something went wrong: rollback
            adapter.rollback_factory_config(self.__key)

            if updater.old_setting is not None:
                self.replace_plugin_filemanager(updater.old_setting["value"]["name"], updater.new_setting["value"])

            raise e

        return ReplacedNLPConfig(name=plugin_filemanager_name, value=updater.new_setting["value"])

    async def remove_cheshire_cat(self, agent_id: str) -> None:
        """
        Removes a Cheshire Cat from the list of active agents.

        Args:
            agent_id: The id of the agent to remove

        Returns:
            None
        """

        if agent_id in self.__cheshire_cats.keys():
            ccat = self.__cheshire_cats[agent_id]
            await ccat.shutdown()

            del self.__cheshire_cats[agent_id]

    def get_cheshire_cat(self, agent_id: str) -> CheshireCat | None:
        """
        Gets the Cheshire Cat with the given id.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """

        if agent_id in self.__cheshire_cats.keys():
            return self.__cheshire_cats[agent_id]

        return None

    def get_or_create_cheshire_cat(self, agent_id: str) -> CheshireCat:
        """
        Gets the Cheshire Cat with the given id, or creates a new one if it doesn't exist.

        Args:
            agent_id: The id of the agent to get or create

        Returns:
            The Cheshire Cat with the given id or a new one if it doesn't exist yet
        """
        current_cat = self.get_cheshire_cat(agent_id)
        if current_cat:  # agent already exists
            return current_cat

        if agent_id == DEFAULT_SYSTEM_KEY:
            raise ValueError(f"{DEFAULT_SYSTEM_KEY} is a reserved name for agents")

        new_cat = CheshireCat(agent_id)
        self.__cheshire_cats[agent_id] = new_cat

        return new_cat

    async def shutdown(self) -> None:
        """
        Shuts down the Bill The Lizard Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """

        for ccat in self.__cheshire_cats.values():
            await ccat.shutdown()
        self.__cheshire_cats = {}

        self.white_rabbit.remove_job(self.__check_idle_strays_job_id)
        self.white_rabbit.shutdown()

        self.white_rabbit = None
        self.core_auth_handler = None
        self.plugin_manager = None
        self.rabbit_hole = None
        self.main_agent = None
        self.embedder = None
        self.embedder_name = None
        self.embedder_size = None
        self.plugin_filemanager = None

    @property
    def cheshire_cats(self):
        return self.__cheshire_cats

    @property
    def config_key(self):
        return self.__key

    @property
    def has_cheshire_cats(self):
        return bool(self.__cheshire_cats)

    @property
    def job_ids(self) -> List:
        return [self.__check_idle_strays_job_id]

    @property
    def mad_hatter(self) -> MadHatter:
        return self.plugin_manager
