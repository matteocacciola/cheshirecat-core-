from typing import Dict

from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.white_rabbit import WhiteRabbit
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
        self.__strays: Dict[str, set[str]] = {} # dictionary with keys as chatbot_id and values the sets of user ids of the strays of that chatbot

        # Start scheduling system
        self.white_rabbit = WhiteRabbit()

        self.core_auth_handler = CoreAuthHandler()

    def __next(self, chatbot_id: str) -> CheshireCat | None:
        return next(
            (cheshire_cat for cheshire_cat in self.__cheshire_cats if cheshire_cat.id == chatbot_id),
            None
        )

    def __any(self, chatbot_id: str) -> bool:
        return any(cheshire_cat.id == chatbot_id for cheshire_cat in self.__cheshire_cats)

    def add_cheshire_cat(self, chatbot_id: str) -> None:
        """
        Adds a new Cheshire Cat to the list of active chatbots.

        Args:
            chatbot_id: The id of the chatbot to add

        Returns:
            None
        """
        if self.__any(chatbot_id):
            return # chatbot already exists

        ccat = CheshireCat(chatbot_id)
        self.__cheshire_cats.add(ccat)

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
        if current_cat:
            return current_cat

        new_chatbot = CheshireCat(chatbot_id)
        self.add_cheshire_cat(chatbot_id)
        return new_chatbot

    def add_stray_to_cheshire_cat(self, chatbot_id: str, user_id: str) -> None:
        """
        Adds a user to the list of strays of a Cheshire Cat. If the Cheshire Cat doesn't exist, it creates a new one.

        Args:
            chatbot_id: The id of the chatbot to add the stray to
            user_id: The id of the user to add as a stray

        Returns:
            None
        """
        self.get_or_create_cheshire_cat(chatbot_id)

        if chatbot_id not in self.__strays:
            self.__strays[chatbot_id] = set()
        self.__strays[chatbot_id].add(user_id)

    def remove_stray_from_cheshire_cat(self, chatbot_id: str, user_id: str) -> None:
        """
        Removes a user from the list of strays of a Cheshire Cat. If the Cheshire Cat doesn't exist, it does nothing.

        Args:
            chatbot_id: The id of the chatbot to remove the stray from
            user_id: The id of the user to remove as a stray

        Returns:
            None
        """

        if not self.__any(chatbot_id):
            return

        if chatbot_id in self.__strays:
            self.__strays[chatbot_id].remove(user_id)

    def get_cheshire_cat_strays(self, chatbot_id: str) -> set[str]:
        """
        Gets the set of strays of a Cheshire Cat. If the Cheshire Cat doesn't exist, it returns an empty set.

        Args:
            chatbot_id: The id of the chatbot to get the strays from

        Returns:
            The set of strays of the Cheshire Cat with the given id, or an empty set if it doesn't exist
        """
        if not self.__any(chatbot_id):
            return set()

        return self.__strays.get(chatbot_id, set())

    def get_cheshire_cat_from_stray(self, stray_user_id: str) -> CheshireCat:
        """
        Gets the Cheshire Cat that has a user as a stray. If the user is not a stray in any chatbot, it raises a
        ValueError. A user cannot be a stray in more than one chatbot at the same time.

        Args:
            stray_user_id: The id of the user to get the Cheshire Cat from that has it as a stray

        Returns:
            The Cheshire Cat that has the user as a stray
        """

        cheshire_cat = next(
            (self.get_cheshire_cat(chatbot_id) for chatbot_id, strays in self.__strays.items() if stray_user_id in strays),
            None
        )

        if not cheshire_cat:
            raise ValueError(f"User {stray_user_id} is not a stray in any chatbot")

        return cheshire_cat
