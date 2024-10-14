import asyncio
from typing import Dict

from cat import utils
from cat.agents.main_agent import MainAgent
from cat.auth.permissions import get_full_admin_permissions
from cat.db import crud, models
from cat.env import get_env
from cat.exceptions import LoadMemoryException
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.factory.embedder import (
    EmbedderSettings,
    EmbedderDumbConfig,
    get_embedder_from_name,
    get_allowed_embedder_models,
)
from cat.log import log
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.utils import singleton


@singleton
class BillTheLizard:
    """
    Singleton class that manages the Cheshire Cats and their strays.

    The Cheshire Cats are the chatbots that are currently active and have users to attend.
    The strays are the users that are waiting for a chatbot to attend them.

    The Bill The Lizard Manager is responsible for:
    - Creating and deleting Cheshire Cats
    - Adding and removing strays from Cheshire Cats
    - Getting the Cheshire Cat of a stray
    - Getting the strays of a Cheshire Cat
    """

    def __init__(self):
        self.__cheshire_cats: Dict[str, CheshireCat] = {}
        self.__key = "core"

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

        if not crud.get_users(self.__key):
            crud.create_basic_users(self.__key, get_full_admin_permissions())

    def load_language_embedder(self) -> EmbedderSettings:
        """Hook into the embedder selection.

        Allows to modify how the Cats select the embedder at bootstrap time.

        Returns
        -------
        embedder : Embeddings
            Selected embedder model.
        """

        selected_embedder = crud.get_setting_by_name(self.__key, "embedder_selected")

        if selected_embedder is not None:
            # get Embedder factory class
            selected_embedder_class = selected_embedder["value"]["name"]
            factory_class = get_embedder_from_name(selected_embedder_class, self.mad_hatter)

            # obtain configuration and instantiate Embedder
            selected_embedder_config = crud.get_setting_by_name(self.__key, selected_embedder_class)
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

    def replace_embedder(self, language_embedder_name: str, settings: Dict) -> Dict:
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
        selected = crud.get_setting_by_name(self.__key, "embedder_selected")

        # create the setting and upsert it
        # embedder type and config are saved in settings table under "embedder_factory" category
        final_setting = crud.upsert_setting_by_name(
            self.__key,
            models.Setting(
                name=language_embedder_name, category="embedder_factory", value=settings
            ),
        )

        # general embedder settings are saved in settings table under "embedder" category
        crud.upsert_setting_by_name(
            self.__key,
            models.Setting(
                name="embedder_selected",
                category="embedder",
                value={"name": language_embedder_name},
            ),
        )

        status = {"name": language_embedder_name, "value": final_setting["value"]}

        # reload the embedder of the cat
        self.embedder = self.load_language_embedder()
        # create new collections (different embedder!)

        for ccat in self.__cheshire_cats.values():
            try:
                ccat.load_memory()
            except Exception as e:  # restore the original Embedder
                log.error(e)

                crud.delete_settings_by_category(self.__key, "embedder")

                # embedder type and config are saved in settings table under "embedder_factory" category
                crud.delete_settings_by_category(self.__key, "embedder_factory")

                # if a selected config is present, restore it
                if selected is not None:
                    self.replace_embedder(selected["value"]["name"], selected)

                raise LoadMemoryException(utils.explicit_error_message(e))

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return status

    def get_selected_embedder_settings(self) -> Dict | None:
        # get selected Embedder settings, if any
        # embedder selected configuration is saved under "embedder_selected" name
        selected = crud.get_setting_by_name(self.__key, "embedder_selected")
        if selected is not None:
            selected = selected["value"]["name"]
        else:
            supported_embedding_models = get_allowed_embedder_models(self.mad_hatter)

            # TODO: take away automatic embedder settings in v2
            # If DB does not contain a selected embedder, it means an embedder was automatically selected.
            # Deduce selected embedder:
            for embedder_config_class in reversed(supported_embedding_models):
                if isinstance(self.embedder, embedder_config_class._pyclass.default):
                    selected = embedder_config_class.__name__

        return selected

    def remove_cheshire_cat(self, chatbot_id: str) -> None:
        """
        Removes a Cheshire Cat from the list of active chatbots.

        Args:
            chatbot_id: The id of the chatbot to remove

        Returns:
            None
        """
        
        if chatbot_id in self.__cheshire_cats.keys():
            del self.__cheshire_cats[chatbot_id]

    def get_cheshire_cat(self, chatbot_id: str) -> CheshireCat | None:
        """
        Gets the Cheshire Cat with the given id.

        Args:
            chatbot_id: The id of the chatbot to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """

        if chatbot_id in self.__cheshire_cats.keys():
            return self.__cheshire_cats[chatbot_id]

        return None

    def get_or_create_cheshire_cat(self, chatbot_id: str) -> CheshireCat:
        """
        Gets the Cheshire Cat with the given id, or creates a new one if it doesn't exist.

        Args:
            chatbot_id: The id of the chatbot to get or create

        Returns:
            The Cheshire Cat with the given id or a new one if it doesn't exist yet
        """
        current_cat = self.get_cheshire_cat(chatbot_id)
        if current_cat:  # chatbot already exists
            return current_cat

        new_cat = CheshireCat(chatbot_id)
        self.__cheshire_cats[chatbot_id] = new_cat

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

    @property
    def cheshire_cats(self):
        return self.__cheshire_cats

    @property
    def config_key(self):
        return self.__key


def job_on_idle_strays(lizard: BillTheLizard, loop) -> bool:
    """
    Remove the objects StrayCat, if idle, from the CheshireCat objects contained into the BillTheLizard.
    """

    ccats = lizard.cheshire_cats.values()

    for ccat in ccats:
        for stray in ccat.strays:
            if stray.is_idle:
                asyncio.run_coroutine_threadsafe(ccat.remove_stray(stray), loop=loop).result()

        if not ccat.has_strays():
            lizard.remove_cheshire_cat(ccat.id)

    return True