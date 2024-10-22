import time
from copy import deepcopy
from typing import List, Dict
from uuid import uuid4
from langchain_community.document_loaders.parsers.pdf import PDFMinerParser
from langchain_community.document_loaders.parsers.html.bs4 import BS4HTMLParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_core.embeddings import Embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from typing_extensions import Protocol
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser

from cat.auth.auth_utils import hash_password
from cat.auth.permissions import get_base_permissions
from cat.db.cruds import settings as crud_settings
from cat.db.cruds import users as crud_users
from cat.factory.adapter import FactoryAdapter
from cat.factory.auth_handler import CoreOnlyAuthConfig, AuthHandlerFactory
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.embedder import EmbedderFactory
from cat.factory.llm import LLMDefaultConfig, LLMFactory
from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.registry import registry_search_plugins
from cat.memory.long_term_memory import LongTermMemory
from cat.utils import langchain_log_prompt, langchain_log_output, get_caller_info


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


class ReplacedLLM(BaseModel):
    installed: List[Dict]
    registry: List[Dict]


# main class
class CheshireCat:
    """The Cheshire Cat.

    This is the main class that manages everything for a single agent.
    """

    def __init__(self, agent_id: str):
        """
        Cat initialization. At init time, the Cat executes the bootstrap.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the LLM, the memories.
        """

        # bootstrap the Cat! ^._.^
        self.id = agent_id

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

        # load LLM
        self.load_language_model()

        # Load memories (vector collections and working_memory)
        self.load_memory()

        # After memory is loaded, we can get/create tools embeddings
        # every time the mad_hatter finishes syncing hooks, tools and forms, it will notify the Cat (so it can embed tools in vector memory)
        self.mad_hatter.on_finish_plugins_sync_callback = self.embed_procedures
        self.embed_procedures()  # first time launched manually

        # Initialize the default user if not present
        if not crud_users.get_users(self.id):
            self.__initialize_users()

        # allows plugins to do something after the cat bootstrap is complete
        self.mad_hatter.execute_hook("after_cat_bootstrap", cat=self)

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"CheshireCat(agent_id={self.id})"

    def __initialize_users(self):
        user_id = str(uuid4())

        crud_users.update_users(self.id, {
            user_id: {
                "id": user_id,
                "username": "user",
                "password": hash_password("user"),
                # user has minor permissions
                "permissions": get_base_permissions(),
            }
        })

    def __next_stray(self, user_id: str) -> "StrayCat":
        """
        Get the next stray from the Cat.
        Args:
            user_id: the user id

        Returns:
            The next StrayCat from the Cat
        """

        return next(
            (stray for stray in self.__strays if stray.user.id == user_id),
            None
        )

    def __any_stray(self, user_id: str) -> bool:
        return any(stray.user.id == user_id for stray in self.__strays)

    def add_stray(self, stray):
        """Add a stray to the Cat."""

        if not self.__any_stray(stray.user.id):
            self.__strays.add(stray)

    async def remove_stray(self, user_id: str):
        """Remove a stray from the Cat."""

        stray = self.__next_stray(user_id)
        if not stray:
            return

        await stray.shutdown()

        self.__strays.remove(stray)
        del stray

    def get_stray(self, user_id: str) -> "StrayCat":
        """Get a stray from the Cat."""

        return self.__next_stray(user_id)

    def has_strays(self) -> bool:
        return bool(self.__strays)

    async def shutdown(self) -> None:
        for stray in self.__strays:
            await stray.shutdown()

        self.__strays.clear()

        self.memory = None
        self.custom_auth_handler = None
        self.mad_hatter = None
        self.llm = None

    def wipe(self):
        """Wipe all data from the cat."""

        self.memory.wipe()
        crud_settings.wipe_settings(self.id)

        # self.memory = None

    def load_language_model(self):
        """Large Language Model (LLM) selection."""

        llm_factory = LLMFactory(self.mad_hatter)

        selected_llm = crud_settings.get_setting_by_name(self.id, llm_factory.setting_name)

        if selected_llm is None:
            # return default LLM
            llm = LLMDefaultConfig.get_llm_from_config({})
        else:
            llm = llm_factory.get_from_config_name(self.id, selected_llm["value"]["name"], )

        embedder_config = EmbedderFactory(
            self.lizard.mad_hatter
        ).get_config_class_from_adapter(self.lizard.embedder.__class__)
        llm_config = llm_factory.get_config_class_from_adapter(llm.__class__)
        if not embedder_config or not llm_config:
            raise ValueError(
                f"Embedder or LLM not found in the list of allowed models."
                f" Embedder: {self.lizard.embedder.__class__}, LLM: {llm.__class__}"
            )

        if embedder_config.is_multimodal() != llm_config.is_multimodal():
            raise ValueError(
                f"Embedder and LLM must be both multimodal or both single modal."
                f" Embedder: {embedder_config.is_multimodal()}, LLM: {llm_config.is_multimodal()}"
            )

        self.llm = llm

    def load_auth(self):
        factory = AuthHandlerFactory(self.mad_hatter)

        # Custom auth_handler
        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.id, CoreOnlyAuthConfig)

        self.custom_auth_handler = factory.get_from_config_name(self.id, selected_config["value"]["name"])

    def load_memory(self):
        """Load LongTerMemory and WorkingMemory."""
        # Memory

        # Get embedder size (langchain classes do not store it)
        embedder_size = len(self.lizard.embedder.embed_query("hello world"))

        # Get embedder name (useful for for vectorstore aliases)
        embedder_name = "default_embedder"
        if hasattr(self.lizard.embedder, "model"):
            embedder_name = self.lizard.embedder.model
        elif hasattr(self.lizard.embedder, "repo_id"):
            embedder_name = self.lizard.embedder.repo_id

        # instantiate long term memory
        vector_memory_config = {
            "embedder_name": embedder_name,
            "embedder_size": embedder_size,
        }
        self.memory = LongTermMemory(vector_memory_config=vector_memory_config, agent_id=self.id)

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
        embedded_procedures, _ = self.memory.vectors.procedural.get_all_points()
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
        points_to_be_deleted = set(embedded_procedures_hashes.keys()) - set(active_procedures_hashes.keys())
        points_to_be_embedded = set(active_procedures_hashes.keys()) - set(embedded_procedures_hashes.keys())

        if points_to_be_deleted_ids := [embedded_procedures_hashes[p] for p in points_to_be_deleted]:
            log.warning(f"Deleting triggers: {points_to_be_deleted}")
            self.memory.vectors.procedural.delete_points(points_to_be_deleted_ids)

        active_triggers_to_be_embedded = [active_procedures_hashes[p] for p in points_to_be_embedded]
        for t in active_triggers_to_be_embedded:
            trigger_embedding = self.lizard.embedder.embed_documents([t["content"]])
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

        Args:
            prompt (str): The prompt for generating the response.

        Returns:
            str: The generated response.
        """

        # Add a token counter to the callbacks
        caller = get_caller_info()

        # here we deal with motherfucking langchain
        prompt = ChatPromptTemplate(messages=[SystemMessage(content=prompt)])

        chain = (
            prompt
            | RunnableLambda(lambda x: langchain_log_prompt(x, f"{caller} prompt"))
            | self.llm
            | RunnableLambda(lambda x: langchain_log_output(x, f"{caller} prompt output"))
            | StrOutputParser()
        )

        # in case we need to pass info to the template
        return chain.invoke({})

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
        registry_plugins_index = {p["url"]: p for p in registry_plugins}

        # get active plugins
        active_plugins = self.mad_hatter.load_active_plugins_from_db()

        # list installed plugins' manifest
        installed_plugins = []
        for p in self.mad_hatter.plugins.values():
            # get manifest
            manifest = deepcopy(p.manifest)  # we make a copy to avoid modifying the plugin obj
            manifest["active"] = (p.id in active_plugins)  # pass along if plugin is active or not
            manifest["upgrade"] = None
            manifest["hooks"] = [{"name": hook.name, "priority": hook.priority} for hook in p.hooks]
            manifest["tools"] = [{"name": tool.name} for tool in p.tools]

            # filter by query
            plugin_text = [str(field) for field in manifest.values()]
            plugin_text = " ".join(plugin_text).lower()
            if query is None or query.lower() in plugin_text:
                for r in registry_plugins:
                    if r["plugin_url"] == p.manifest["plugin_url"] and r["version"] != p.manifest["version"]:
                        manifest["upgrade"] = r["version"]
                installed_plugins.append(manifest)

            # do not show already installed plugins among registry plugins
            registry_plugins_index.pop(manifest["plugin_url"], None)

        return Plugins(installed=installed_plugins, registry=list(registry_plugins_index.values()))

    def replace_llm(self, language_model_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current LLM with a new one. This method is used to change the LLM of the cat.
        Args:
            language_model_name: name of the new LLM
            settings: settings of the new LLM

        Returns:
            The dictionary resuming the new name and settings of the LLM
        """

        adapter = FactoryAdapter(LLMFactory(self.mad_hatter))

        updater = adapter.upsert_factory_config_by_settings(self.id, language_model_name, settings)
        # if the llm is the same, return the old one, i.e. there is no new factory llm
        if not updater.new_factory:
            return ReplacedNLPConfig(name=language_model_name, value=updater.old_factory.get("value"))

        try:
            # try to reload the llm of the cat
            self.load_language_model()
        except ValueError as e:
            log.error(f"Error while loading the new LLM: {e}")

            # something went wrong: rollback
            adapter.rollback_factory_config(self.id)

            if updater.old_setting is not None:
                self.replace_llm(updater.old_setting["value"]["name"], updater.new_factory["value"])

            raise e

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return ReplacedNLPConfig(name=language_model_name, value=updater.new_factory["value"])

    def replace_auth_handler(self, auth_handler_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current Auth Handler with a new one.
        Args:
            auth_handler_name: name of the new Auth Handler
            settings: settings of the new Auth Handler

        Returns:
            The dictionary resuming the new name and settings of the Auth Handler
        """

        updater = FactoryAdapter(
            AuthHandlerFactory(self.mad_hatter)
        ).upsert_factory_config_by_settings(self.id, auth_handler_name, settings)

        # if the auth handler is the same, return the old one, i.e. there is no new factory auth handler
        if not updater.new_factory:
            return ReplacedNLPConfig(name=auth_handler_name, value=updater.old_factory.get("value"))

        self.load_auth()

        return ReplacedNLPConfig(name=auth_handler_name, value=updater.new_factory["value"])

    @property
    def lizard(self) -> "BillTheLizard":
        from cat.bill_the_lizard import BillTheLizard
        return BillTheLizard()

    @property
    def strays(self):
        return self.__strays

    @property
    def embedder(self) -> Embeddings:
        return self.lizard.embedder

    @property
    def rabbit_hole(self) -> "RabbitHole":
        return self.lizard.rabbit_hole

    @property
    def core_auth_handler(self) -> "CoreAuthHandler":
        return self.lizard.core_auth_handler

    @property
    def main_agent(self) -> "MainAgent":
        return self.lizard.main_agent

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        # default file handlers
        file_handlers = {
            "application/pdf": PDFMinerParser(),
            "text/plain": TextParser(),
            "text/markdown": TextParser(),
            "text/html": BS4HTMLParser(),
        }

        # no access to stray
        file_handlers = self.mad_hatter.execute_hook(
            "rabbithole_instantiates_parsers", file_handlers, cat=self
        )

        return file_handlers

    # each time we access the text splitter, plugins can intervene
    @property
    def text_splitter(self):
        # default text splitter
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=256,
            chunk_overlap=64,
            separators=["\\n\\n", "\n\n", ".\\n", ".\n", "\\n", "\n", " ", ""],
            encoding_name="cl100k_base",
            keep_separator=True,
            strip_whitespace=True,
        )

        # no access to stray
        text_splitter = self.mad_hatter.execute_hook(
            "rabbithole_instantiates_splitter", text_splitter, cat=self
        )
        return text_splitter
