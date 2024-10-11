import time
from copy import deepcopy
from typing import List, Dict
from pydantic import BaseModel
from typing_extensions import Protocol
from langchain.base_language import BaseLanguageModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from langchain_community.llms import Cohere
from langchain_openai import ChatOpenAI, OpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from cat.agents.main_agent import MainAgent
from cat.exceptions import LoadMemoryException
import cat.factory.auth_handler as auth_handlers
from cat.db import crud, models
from cat.factory.embedder import (
    EmbedderSettings,
    EmbedderDumbConfig,
    EmbedderOpenAIConfig,
    EmbedderCohereConfig,
    EmbedderGeminiChatConfig,
    get_embedder_from_name,
    get_allowed_embedder_models,
)
from cat.factory.llm import LLMDefaultConfig
from cat.factory.llm import get_llm_from_name
from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.registry import registry_search_plugins
from cat.memory.long_term_memory import LongTermMemory
from cat.rabbit_hole import RabbitHole
from cat import utils


class Procedure(Protocol):
    name: str
    procedure_type: str  # "tool" or "form"

    # {
    #   "description": [],
    #   "start_examples": [],
    # }
    triggers_map: Dict[str, List[str]]


class Plugins(BaseModel):
    installed: List[Dict]
    registry: List[Dict]


# main class
class CheshireCat:
    """The Cheshire Cat.

    This is the main class that manages everything for a single chatbot.
    """

    def __init__(self, chatbot_id: str):
        """Cat initialization.

        At init time the Cat executes the bootstrap.
        """

        # bootstrap the Cat! ^._.^
        self.id = chatbot_id

        self.embedder = None
        self.llm = None
        self.memory = None
        self.custom_auth_handler = None

        self.__strays: set = set()  # set of StrayCat instances

        # instantiate MadHatter (loads all plugins' hooks and tools)
        self.mad_hatter = MadHatter(self.id)

        # load AuthHandler
        self.load_auth()

        # allows plugins to do something before cat components are loaded
        self.mad_hatter.execute_hook("before_cat_bootstrap", cat=self)

        # load LLM and embedder
        self.load_natural_language()

        # Load memories (vector collections and working_memory)
        self.load_memory()

        # After memory is loaded, we can get/create tools embeddings
        # every time the mad_hatter finishes syncing hooks, tools and forms, it will notify the Cat (so it can embed tools in vector memory)
        self.mad_hatter.on_finish_plugins_sync_callback = self.embed_procedures
        self.embed_procedures()  # first time launched manually

        # Main agent instance (for reasoning)
        self.main_agent = MainAgent()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole(self)

        # allows plugins to do something after the cat bootstrap is complete
        self.mad_hatter.execute_hook("after_cat_bootstrap", cat=self)

        self.__create_basic_users_if_not_exist()

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __next_stray(self, user_id: str):
        """
        Get the next stray from the Cat.
        Args:
            user_id: the user id

        Returns:
            The next StrayCat from the Cat
        """

        return next(
            (cat for cat in self.__strays if cat.user_id == user_id),
            None
        )

    def __any_stray(self, user_id: str) -> bool:
        return any(cat.user_id == user_id for cat in self.__strays)

    def add_stray(self, stray):
        """Add a stray to the Cat."""

        if not self.__any_stray(stray.user_id):
            self.__strays.add(stray)

    def remove_stray(self, user_id: str):
        """Remove a stray from the Cat."""

        stray = self.__next_stray(user_id)
        if not stray:
            return

        stray.ws.close()
        self.__strays.remove(stray)

        del stray

    def get_stray(self, user_id: str):
        """Get a stray from the Cat."""

        return self.__next_stray(user_id)

    def has_strays(self) -> bool:
        return bool(self.__strays)

    def shutdown(self) -> None:
        for stray in self.__strays:
            if stray.ws:
                stray.ws.close()

        self.__strays.clear()

    def load_natural_language(self):
        """Load Natural Language related objects.

        The method exposes in the Cat all the NLP related stuff. Specifically, it sets the language models
        (LLM and Embedder).

        Warnings
        --------
        When using small Language Models it is suggested to turn off the memories and make the main prompt smaller
        to prevent them to fail.

        See Also
        --------
        agent_prompt_prefix
        """
        # LLM and embedder
        self.llm = self.load_language_model()
        self.embedder = self.load_language_embedder()

    def load_language_model(self) -> BaseLanguageModel:
        """Large Language Model (LLM) selection.

        Returns
        -------
        llm : BaseLanguageModel
            Langchain `BaseLanguageModel` instance of the selected model.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories,
        the *Main Agent*, the *Rabbit Hole* and the *White Rabbit*.

        """

        selected_llm = crud.get_setting_by_name(name="llm_selected", chatbot_id=self.id)

        if selected_llm is None:
            # return default LLM
            llm = LLMDefaultConfig.get_llm_from_config({})
        else:
            # get LLM factory class
            selected_llm_class = selected_llm["value"]["name"]
            factory_class = get_llm_from_name(selected_llm_class, self.mad_hatter)

            # obtain configuration and instantiate LLM
            selected_llm_config = crud.get_setting_by_name(name=selected_llm_class, chatbot_id=self.id)
            try:
                llm = factory_class.get_llm_from_config(selected_llm_config["value"])
            except Exception:
                import traceback

                traceback.print_exc()
                llm = LLMDefaultConfig.get_llm_from_config({})

        return llm

    def load_language_embedder(self) -> EmbedderSettings:
        """Hook into the  embedder selection.

        Allows to modify how the Cat selects the embedder at bootstrap time.

        Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories,
        the *Main Agent*, the *Rabbit Hole* and the *White Rabbit*.

        Returns
        -------
        embedder : Embeddings
            Selected embedder model.
        """
        # Embedding LLM

        selected_embedder = crud.get_setting_by_name(name="embedder_selected", chatbot_id=self.id)

        if selected_embedder is not None:
            # get Embedder factory class
            selected_embedder_class = selected_embedder["value"]["name"]
            factory_class = get_embedder_from_name(selected_embedder_class, self.mad_hatter)

            # obtain configuration and instantiate Embedder
            selected_embedder_config = crud.get_setting_by_name(name=selected_embedder_class, chatbot_id=self.id)
            try:
                embedder = factory_class.get_embedder_from_config(selected_embedder_config["value"])
            except AttributeError:
                import traceback

                traceback.print_exc()
                embedder = EmbedderDumbConfig.get_embedder_from_config({})
            return embedder

        llm_type = type(self.llm)

        # OpenAI embedder
        if llm_type in [OpenAI, ChatOpenAI]:
            return EmbedderOpenAIConfig.get_embedder_from_config(
                {
                    "openai_api_key": self.llm.openai_api_key,
                }
            )

        # For Azure avoid automatic embedder selection

        # Cohere
        if llm_type in [Cohere]:
            return EmbedderCohereConfig.get_embedder_from_config(
                {
                    "cohere_api_key": self.llm.cohere_api_key,
                    "model": "embed-multilingual-v2.0",
                    # Now the best model for embeddings is embed-multilingual-v2.0
                }
            )

        if llm_type in [ChatGoogleGenerativeAI]:
            return EmbedderGeminiChatConfig.get_embedder_from_config(
                {
                    "model": "models/embedding-001",
                    "google_api_key": self.llm.google_api_key,
                }
            )

        # If no embedder matches vendor, and no external embedder is configured, we use the DumbEmbedder.
        #   `This embedder is not a model properly trained
        #    and this makes it not suitable to effectively embed text,
        #    "but it does not know this and embeds anyway".` - cit. Nicola Corbellini
        return EmbedderDumbConfig.get_embedder_from_config({})

    def load_auth(self):
        # Custom auth_handler # TODOAUTH: change the name to custom_auth
        selected_auth_handler = crud.get_setting_by_name(name="auth_handler_selected", chatbot_id=self.id)

        # if no auth_handler is saved, use default one and save to db
        if selected_auth_handler is None:
            # create the auth settings
            crud.upsert_setting_by_name(
                models.Setting(
                    name="CoreOnlyAuthConfig", category="auth_handler_factory", value={}
                ),
                chatbot_id=self.id,
            )
            crud.upsert_setting_by_name(
                models.Setting(
                    name="auth_handler_selected",
                    category="auth_handler_factory",
                    value={"name": "CoreOnlyAuthConfig"},
                ),
                chatbot_id=self.id,
            )

            # reload from db
            selected_auth_handler = crud.get_setting_by_name(name="auth_handler_selected", chatbot_id=self.id)

        # get AuthHandler factory class
        selected_auth_handler_class = selected_auth_handler["value"]["name"]
        factory_class = auth_handlers.get_auth_handler_from_name(selected_auth_handler_class, self.mad_hatter)

        # obtain configuration and instantiate AuthHandler
        selected_auth_handler_config = crud.get_setting_by_name(name=selected_auth_handler_class, chatbot_id=self.id)
        try:
            auth_handler = factory_class.get_auth_handler_from_config(selected_auth_handler_config["value"])
        except Exception:
            import traceback
            traceback.print_exc()

            auth_handler = auth_handlers.CoreOnlyAuthConfig.get_auth_handler_from_config({})

        self.custom_auth_handler = auth_handler

    def load_memory(self):
        """Load LongTerMemory and WorkingMemory."""
        # Memory

        # Get embedder size (langchain classes do not store it)
        embedder_size = len(self.embedder.embed_query("hello world"))

        # Get embedder name (useful for for vectorstore aliases)
        embedder_name = "default_embedder"
        if hasattr(self.embedder, "model"):
            embedder_name = self.embedder.model
        elif hasattr(self.embedder, "repo_id"):
            embedder_name = self.embedder.repo_id

        # instantiate long term memory
        vector_memory_config = {
            "embedder_name": embedder_name,
            "embedder_size": embedder_size,
        }
        self.memory = LongTermMemory(vector_memory_config=vector_memory_config, chatbot_id=self.id)

    def embed_procedures(self):
        def get_key_embedded_procedures_hashes(ep):
            # log.warning(ep)
            metadata = ep.payload["metadata"]
            content = ep.payload["page_content"]
            source = metadata["source"]
            # there may be legacy points with no trigger_type
            trigger_type = metadata.get("trigger_type", "unsupported")
            return f"{source}.{trigger_type}.{content}"

        def get_key_active_procedures_hashes(ap, trigger_type, trigger_content):
            return f"{ap.name}.{trigger_type}.{trigger_content}"

        # Retrieve from vectorDB all procedural embeddings
        embedded_procedures = self.memory.vectors.procedural.get_all_points()
        embedded_procedures_hashes = {get_key_embedded_procedures_hashes(ep): ep.id for ep in embedded_procedures}

        # Easy access to active procedures in mad_hatter (source of truth!)
        active_procedures_hashes = {get_key_active_procedures_hashes(ap, trigger_type, trigger_content): {
            "obj": ap,
            "source": ap.name,
            "type": ap.procedure_type,
            "trigger_type": trigger_type,
            "content": trigger_content,
        } for ap in self.mad_hatter.procedures for trigger_type, trigger_list in ap.triggers_map.items() for
            trigger_content in trigger_list}

        # points_to_be_kept = set(active_procedures_hashes.keys()) and set(embedded_procedures_hashes.keys()) not necessary
        points_to_be_deleted = set(embedded_procedures_hashes.keys()) - set(
            active_procedures_hashes.keys()
        )
        points_to_be_embedded = set(active_procedures_hashes.keys()) - set(
            embedded_procedures_hashes.keys()
        )

        if points_to_be_deleted_ids := [embedded_procedures_hashes[p] for p in points_to_be_deleted]:
            log.warning(f"Deleting triggers: {points_to_be_deleted}")
            self.memory.vectors.procedural.delete_points(points_to_be_deleted_ids)

        active_triggers_to_be_embedded = [active_procedures_hashes[p] for p in points_to_be_embedded]
        for t in active_triggers_to_be_embedded:
            trigger_embedding = self.embedder.embed_documents([t["content"]])
            self.memory.vectors.procedural.add_point(
                t["content"],
                trigger_embedding[0],
                {
                    "source": t["source"],
                    "type": t["type"],
                    "trigger_type": t["trigger_type"],
                    "when": time.time(),
                },
            )

            log.warning(
                f"Newly embedded {t['type']} trigger: {t['source']}, {t['trigger_type']}, {t['content']}"
            )

    def send_ws_message(self, content: str, msg_type="notification"):
        log.error("No websocket connection open")

    # REFACTOR: cat.llm should be available here, without streaming clearly
    # (one could be interested in calling the LLM anytime, not only when there is a session)
    def llm_response(self, prompt, *args, **kwargs) -> str:
        """Generate a response using the LLM model.

        This method is useful for generating a response with both a chat and a completion model using the same syntax

        Parameters
        ----------
        prompt : str
            The prompt for generating the response.

        Returns
        -------
        str
            The generated response.

        """

        # Add a token counter to the callbacks
        caller = utils.get_caller_info()

        # here we deal with motherfucking langchain
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessage(content=prompt)
            ]
        )

        chain = (
            prompt
            | RunnableLambda(lambda x: utils.langchain_log_prompt(x, f"{caller} prompt"))
            | self.llm
            | RunnableLambda(lambda x: utils.langchain_log_output(x, f"{caller} prompt output"))
            | StrOutputParser()
        )

        output = chain.invoke(
            {}, # in case we need to pass info to the template
        )

        return output

    async def get_plugins(self, query: str = None) -> Plugins:
        """
        Get the plugins related to the current Cheshire Cat
        Args:
            query: the query to look for

        Returns:
            The list of plugins
        """
        # retrieve plugins from official repo
        registry_plugins = await registry_search_plugins(query)
        # index registry plugins by url
        registry_plugins_index = {}
        for p in registry_plugins:
            plugin_url = p["url"]
            registry_plugins_index[plugin_url] = p

        # get active plugins
        active_plugins = self.mad_hatter.load_active_plugins_from_db()

        # list installed plugins' manifest
        installed_plugins = []
        for p in self.mad_hatter.plugins.values():
            # get manifest
            manifest = deepcopy(
                p.manifest
            )  # we make a copy to avoid modifying the plugin obj
            manifest["active"] = (
                    p.id in active_plugins
            )  # pass along if plugin is active or not
            manifest["upgrade"] = None
            manifest["hooks"] = [
                {"name": hook.name, "priority": hook.priority} for hook in p.hooks
            ]
            manifest["tools"] = [{"name": tool.name} for tool in p.tools]

            # filter by query
            plugin_text = [str(field) for field in manifest.values()]
            plugin_text = " ".join(plugin_text).lower()
            if (query is None) or (query.lower() in plugin_text):
                for r in registry_plugins:
                    if r["plugin_url"] == p.manifest["plugin_url"]:
                        if r["version"] != p.manifest["version"]:
                            manifest["upgrade"] = r["version"]
                installed_plugins.append(manifest)

            # do not show already installed plugins among registry plugins
            registry_plugins_index.pop(manifest["plugin_url"], None)

        return Plugins(installed=installed_plugins, registry=list(registry_plugins_index.values()))

    def replace_llm(self, language_model_name: str, settings: Dict) -> Dict:
        """
        Replace the current LLM with a new one. This method is used to change the LLM of the cat.
        Args:
            language_model_name: name of the new LLM
            settings: settings of the new LLM

        Returns:
            The dictionary resuming the new name and settings of the LLM
        """
        # create the setting and upsert it
        final_setting = crud.upsert_setting_by_name(
            models.Setting(name=language_model_name, category="llm_factory", value=settings),
            chatbot_id=self.id
        )

        # general LLM settings are saved in settings table under "llm" category
        crud.upsert_setting_by_name(
            models.Setting(name="llm_selected", category="llm", value={"name": language_model_name}),
            chatbot_id=self.id
        )

        status = {"name": language_model_name, "value": final_setting["value"]}

        # reload llm and embedder of the cat
        self.load_natural_language()

        # create new collections
        # (in case embedder is not configured, it will be changed automatically and aligned to vendor)
        # TODO: should we take this feature away?
        # Exception handling in case an incorrect key is loaded.
        try:
            self.load_memory()
        except Exception as e:
            log.error(e)
            crud.delete_settings_by_category(category="llm", chatbot_id=self.id)
            crud.delete_settings_by_category(category="llm_factory", chatbot_id=self.id)

            raise LoadMemoryException(utils.explicit_error_message(e))

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return status

    def get_selected_embedder_settings(self) -> Dict | None:
        # get selected Embedder settings, if any
        # embedder selected configuration is saved under "embedder_selected" name
        selected = crud.get_setting_by_name(name="embedder_selected", chatbot_id=self.id)
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

    def replace_embedder(self, language_embedder_name: str, settings: Dict) -> Dict:
        """
        Replace the current embedder with a new one. This method is used to change the embedder of the cat.
        Args:
            language_embedder_name: name of the new embedder
            settings: settings of the new embedder

        Returns:
            The dictionary resuming the new name and settings of the embedder
        """
        # get selected config if any
        # embedder selected configuration is saved under "embedder_selected" name
        selected = crud.get_setting_by_name(name="embedder_selected", chatbot_id=self.id)

        # create the setting and upsert it
        # embedder type and config are saved in settings table under "embedder_factory" category
        final_setting = crud.upsert_setting_by_name(
            models.Setting(
                name=language_embedder_name, category="embedder_factory", value=settings
            ),
            chatbot_id=self.id
        )

        # general embedder settings are saved in settings table under "embedder" category
        crud.upsert_setting_by_name(
            models.Setting(
                name="embedder_selected",
                category="embedder",
                value={"name": language_embedder_name},
            ),
            chatbot_id=self.id
        )

        status = {"name": language_embedder_name, "value": final_setting["value"]}

        # reload llm and embedder of the cat
        self.load_natural_language()
        # crete new collections (different embedder!)
        try:
            self.load_memory()
        except Exception as e:
            log.error(e)

            crud.delete_settings_by_category(category="embedder", chatbot_id=self.id)

            # embedder type and config are saved in settings table under "embedder_factory" category
            crud.delete_settings_by_category(category="embedder_factory", chatbot_id=self.id)

            # if a selected config is present, restore it
            if selected is not None:
                current_settings = crud.get_setting_by_name(name=selected["value"]["name"], chatbot_id=self.id)

                language_embedder_name = selected["value"]["name"]
                crud.upsert_setting_by_name(
                    models.Setting(
                        name=language_embedder_name,
                        category="embedder_factory",
                        value=current_settings["value"],
                    ),
                    chatbot_id=self.id
                )

                # embedder selected configuration is saved under "embedder_selected" name
                crud.upsert_setting_by_name(
                    models.Setting(
                        name="embedder_selected",
                        category="embedder",
                        value={"name": language_embedder_name},
                    ),
                    chatbot_id=self.id
                )
                # reload llm and embedder of the cat
                self.load_natural_language()

            raise LoadMemoryException(utils.explicit_error_message(e))

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return status

    def __create_basic_users_if_not_exist(self):
        if not crud.get_users(chatbot_id=self.id):
            crud.create_basic_users(chatbot_id=self.id)

    @property
    def strays(self):
        return self.__strays
