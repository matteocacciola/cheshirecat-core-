import time
from typing import List, Dict
from typing_extensions import Protocol

from langchain.base_language import BaseLanguageModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from langchain_community.llms import Cohere
from langchain_openai import ChatOpenAI, OpenAI
from langchain_google_genai import ChatGoogleGenerativeAI

from cat.factory.auth_handler import get_auth_handler_from_name
import cat.factory.auth_handler as auth_handlers
from cat.db import crud, models
from cat.factory.embedder import (
    EmbedderSettings,
    EmbedderDumbConfig,
    EmbedderOpenAIConfig,
    EmbedderCohereConfig,
    EmbedderGeminiChatConfig,
    get_embedder_from_name,
)
from cat.factory.llm import LLMDefaultConfig
from cat.factory.llm import get_llm_from_name
from cat.agents.main_agent import MainAgent
from cat.log import log
from cat.looking_glass.stray_cat import StrayCat
from cat.mad_hatter.mad_hatter import MadHatter
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

        self.__strays: set[StrayCat] = set()

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
        self.rabbit_hole = RabbitHole(self.id)

        # allows plugins to do something after the cat bootstrap is complete
        self.mad_hatter.execute_hook("after_cat_bootstrap", cat=self)

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __next_stray(self, user_id: str) -> StrayCat | None:
        return next(
            (cat for cat in self.__strays if cat.user_id == user_id),
            None
        )

    def __any_stray(self, user_id: str) -> bool:
        return any(cat.user_id == user_id for cat in self.__strays)

    def add_stray(self, stray: StrayCat):
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

    def get_stray(self, user_id: str) -> StrayCat | None:
        """Get a stray from the Cat."""

        return self.__next_stray(user_id)

    def has_strays(self) -> bool:
        return bool(self.__strays)

    def shutdown(self) -> None:
        for stray in self.__strays:
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
            factory_class = get_llm_from_name(selected_llm_class, self.id)

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
            factory_class = get_embedder_from_name(selected_embedder_class, self.id)

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
        factory_class = get_auth_handler_from_name(selected_auth_handler_class, self.id)

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
        if hasattr(self.embedder, "model"):
            embedder_name = self.embedder.model
        elif hasattr(self.embedder, "repo_id"):
            embedder_name = self.embedder.repo_id
        else:
            embedder_name = "default_embedder"

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

    @property
    def strays(self):
        return self.__strays
