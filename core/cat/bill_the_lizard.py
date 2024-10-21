import asyncio
from typing import Dict, List
from uuid import uuid4
from langchain_core.embeddings import Embeddings

from cat import utils
from cat.agents.main_agent import MainAgent
from cat.auth.auth_utils import hash_password
from cat.auth.permissions import get_full_admin_permissions
from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.db.cruds import users as crud_users
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.env import get_env
from cat.exceptions import LoadMemoryException
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.factory.embedder import EmbedderDumbConfig, get_embedder_factory_from_config_name, get_allowed_embedder_models
from cat.jobs import job_on_idle_strays
from cat.log import log
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.utils import singleton, ReplacedNLPConfig


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
        self.__cheshire_cats: Dict[str, CheshireCat] = {}
        self.__key = DEFAULT_SYSTEM_KEY

        # Start scheduling system
        self.white_rabbit = WhiteRabbit()
        self.__check_idle_strays_job_id = self.white_rabbit.schedule_cron_job(
            lambda: job_on_idle_strays(self, asyncio.new_event_loop()), second=int(get_env("CCAT_STRAYCAT_TIMEOUT"))
        )

        self.mad_hatter = MadHatter(self.__key)

        # load LLM and embedder
        self.embedder = self.load_language_embedder()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # Main agent instance (for reasoning)
        self.main_agent = MainAgent()

        # Initialize the default admin if not present
        if not crud_users.get_users(self.__key):
            self.__initialize_users()

    def __initialize_users(self):
        admin_id = str(uuid4())

        crud_users.update_users(self.__key, {
            admin_id: {
                "id": admin_id,
                "username": "admin",
                "password": hash_password(get_env("CCAT_ADMIN_DEFAULT_PASSWORD")),
                # admin has all permissions
                "permissions": get_full_admin_permissions()
            }
        })

    def load_language_embedder(self) -> Embeddings:
        """Hook into the embedder selection.

        Allows to modify how the Cats select the embedder at bootstrap time.

        Returns:
            Selected embedder model.
        """

        selected_embedder = crud_settings.get_setting_by_name(self.__key, "embedder_selected")

        if selected_embedder is not None:
            # get Embedder factory class
            selected_embedder_class = selected_embedder["value"]["name"]
            factory_class = get_embedder_factory_from_config_name(selected_embedder_class, self.mad_hatter)

            # obtain configuration and instantiate Embedder
            selected_embedder_config = crud_settings.get_setting_by_name(self.__key, selected_embedder_class)
            try:
                embedder = factory_class.get_embedder_from_config(selected_embedder_config["value"])
            except AttributeError:
                import traceback

                traceback.print_exc()
                embedder = EmbedderDumbConfig.get_embedder_from_config({})
            return embedder

        # If no embedder matches vendor, and no external embedder is configured, we use the DumbEmbedder.
        #   `This embedder is not a model properly trained
        #    and this makes it not suitable to effectively embed text,
        #    "but it does not know this and embeds anyway".` - cit. Nicola Corbellini
        return EmbedderDumbConfig.get_embedder_from_config({})

    def replace_embedder(self, language_embedder_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current embedder with a new one. This method is used to change the embedder of the cats.

        Args:
            language_embedder_name: name of the new embedder
            settings: settings of the new embedder

        Returns:
            The dictionary resuming the new name and settings of the embedder
        """

        # get selected config if any
        # embedder selected configuration is saved under "embedder_selected" name
        selected = crud_settings.get_setting_by_name(self.__key, "embedder_selected")

        # create the setting and upsert it
        # embedder type and config are saved in settings table under "embedder_factory" category
        final_setting = crud_settings.upsert_setting_by_name(
            self.__key,
            models.Setting(
                name=language_embedder_name, category="embedder_factory", value=settings
            ),
        )

        # general embedder settings are saved in settings table under "embedder" category
        crud_settings.upsert_setting_by_name(
            self.__key,
            models.Setting(
                name="embedder_selected",
                category="embedder",
                value={"name": language_embedder_name},
            ),
        )

        # reload the embedder of the cat
        self.embedder = self.load_language_embedder()
        # create new collections (different embedder!)

        for ccat in self.__cheshire_cats.values():
            try:
                ccat.load_memory()
            except Exception as e:  # restore the original Embedder
                log.error(e)

                crud_settings.delete_settings_by_category(self.__key, "embedder")

                # embedder type and config are saved in settings table under "embedder_factory" category
                crud_settings.delete_settings_by_category(self.__key, "embedder_factory")

                # if a selected config is present, restore it
                if selected is not None:
                    self.replace_embedder(selected["value"]["name"], selected)

                raise LoadMemoryException(f"Load memory exception: {utils.explicit_error_message(e)}")

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return ReplacedNLPConfig(name=language_embedder_name, value=final_setting["value"])

    def get_selected_embedder_settings(self) -> str | None:
        # get selected Embedder settings, if any
        # embedder selected configuration is saved under "embedder_selected" name
        selected = crud_settings.get_setting_by_name(self.__key, "embedder_selected")
        if selected is not None:
            return selected["value"]["name"]

        supported_embedding_models = get_allowed_embedder_models(self.mad_hatter)

        # TODO: take away automatic embedder settings in v2
        # If DB does not contain a selected embedder, it means an embedder was automatically selected.
        # Deduce selected embedder:
        return next((
            embedder_config_class.__name__
            for embedder_config_class in reversed(supported_embedding_models)
            if isinstance(self.embedder, embedder_config_class._pyclass.default)),
            None
        )

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

        self.white_rabbit = None
        self.core_auth_handler = None
        self.mad_hatter = None
        self.rabbit_hole = None
        self.main_agent = None
        self.embedder = None

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
