import asyncio

from cat.agents.main_agent import MainAgent
from cat.env import get_env
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.utils import singleton


@singleton
class CheshireCatManager:
    """
    Singleton class that manages the Cheshire Cats and their strays.

    The Cheshire Cats are the chatbots that are currently active and have users to attend.
    The strays are the users that are waiting for a chatbot to attend them.

    The Cheshire Cat Manager is responsible for:
    - Creating and deleting Cheshire Cats
    - Adding and removing strays from Cheshire Cats
    - Getting the Cheshire Cat of a stray
    - Getting the strays of a Cheshire Cat
    """

    def __init__(self):
        self.__cheshire_cats: set[CheshireCat] = set()

        # Start scheduling system
        self.white_rabbit = WhiteRabbit()
        self.__check_idle_strays_job_id = self.white_rabbit.schedule_cron_job(
            lambda: job_on_idle_strays(self, asyncio.new_event_loop()), second=int(get_env("CCAT_STRAYCAT_TIMEOUT"))
        )

        self.mad_hatter = MadHatter("core")

        self.core_auth_handler = CoreAuthHandler()

        # Main agent instance (for reasoning)
        self.main_agent = MainAgent()

    def __next(self, chatbot_id: str) -> CheshireCat | None:
        return next(
            (cheshire_cat for cheshire_cat in self.__cheshire_cats if cheshire_cat.id == chatbot_id),
            None
        )

    def __any(self, chatbot_id: str) -> bool:
        return any(cheshire_cat.id == chatbot_id for cheshire_cat in self.__cheshire_cats)

    def remove_cheshire_cat(self, chatbot_id: str) -> None:
        """
        Removes a Cheshire Cat from the list of active chatbots.

        Args:
            chatbot_id: The id of the chatbot to remove

        Returns:
            None
        """
        cheshire_cat = self.__next(chatbot_id)
        if cheshire_cat:
            self.__cheshire_cats.remove(cheshire_cat)

    def get_cheshire_cat(self, chatbot_id: str) -> CheshireCat | None:
        """
        Gets the Cheshire Cat with the given id.

        Args:
            chatbot_id: The id of the chatbot to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        return self.__next(chatbot_id)

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
        self.__cheshire_cats.add(new_cat)

        return new_cat

    async def shutdown(self) -> None:
        """
        Shuts down the Cheshire Cat Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """
        for ccat in self.__cheshire_cats:
            await ccat.shutdown()
        self.__cheshire_cats.clear()

        self.white_rabbit.remove_job(self.__check_idle_strays_job_id)

        self.white_rabbit = None
        self.core_auth_handler = None

    @property
    def cheshire_cats(self):
        return self.__cheshire_cats


def job_on_idle_strays(cat_manager: CheshireCatManager, loop) -> bool:
    """
    Remove the objects StrayCat, if idle, from the CheshireCat objects contained into the CheshireCatManager.
    """

    ccats = cat_manager.cheshire_cats

    for ccat in ccats:
        for stray in ccat.strays:
            if stray.is_idle:
                asyncio.run_coroutine_threadsafe(ccat.remove_stray(stray), loop=loop).result()

        if not ccat.has_strays():
            cat_manager.remove_cheshire_cat(ccat.id)

    return True