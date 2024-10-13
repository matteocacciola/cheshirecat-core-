import time
from copy import deepcopy
from typing import List, Dict
from langchain_community.document_loaders.parsers.pdf import PDFMinerParser
from langchain_community.document_loaders.parsers.html.bs4 import BS4HTMLParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pydantic import BaseModel
from typing_extensions import Protocol
from langchain.base_language import BaseLanguageModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser

import cat.factory.auth_handler as auth_handlers
from cat.db import crud, models
from cat.factory.embedder import EmbedderSettings
from cat.factory.llm import LLMDefaultConfig
from cat.factory.llm import get_llm_from_name
from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.registry import registry_search_plugins
from cat.mad_hatter.utils import execute_hook
from cat.memory.long_term_memory import LongTermMemory
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

        self.memory = None
        self.custom_auth_handler = None

        self.__strays: set = set()  # set of StrayCat instances

        # instantiate MadHatter (loads all plugins' hooks and tools)
        self.mad_hatter = MadHatter(self.id)

        # load AuthHandler
        self.load_auth()

        # allows plugins to do something before cat components are loaded
        execute_hook(self.mad_hatter, "before_cat_bootstrap", cat=self)

        # load LLM
        self.llm = self.load_language_model()

        # Load memories (vector collections and working_memory)
        self.load_memory()

        # After memory is loaded, we can get/create tools embeddings
        # every time the mad_hatter finishes syncing hooks, tools and forms, it will notify the Cat (so it can embed tools in vector memory)
        self.mad_hatter.on_finish_plugins_sync_callback = self.embed_procedures
        self.embed_procedures()  # first time launched manually

        # allows plugins to do something after the cat bootstrap is complete
        execute_hook(self.mad_hatter, "after_cat_bootstrap", cat=self)

        if not crud.get_users(self.id):
            crud.create_basic_users(self.id)

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

    async def remove_stray(self, user_id: str):
        """Remove a stray from the Cat."""

        stray = self.__next_stray(user_id)
        if not stray:
            return

        await stray.ws.close()
        self.__strays.remove(stray)

        del stray

    def get_stray(self, user_id: str):
        """Get a stray from the Cat."""

        return self.__next_stray(user_id)

    def has_strays(self) -> bool:
        return bool(self.__strays)

    async def shutdown(self) -> None:
        for stray in self.__strays:
            if stray.ws:
                await stray.ws.close()

        self.__strays.clear()

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

        selected_llm = crud.get_setting_by_name(self.id, "llm_selected")

        if selected_llm is None:
            # return default LLM
            llm = LLMDefaultConfig.get_llm_from_config({})
        else:
            # get LLM factory class
            selected_llm_class = selected_llm["value"]["name"]
            factory_class = get_llm_from_name(selected_llm_class, self.mad_hatter)

            # obtain configuration and instantiate LLM
            selected_llm_config = crud.get_setting_by_name(self.id, selected_llm_class)
            try:
                llm = factory_class.get_llm_from_config(selected_llm_config["value"])
            except Exception:
                import traceback

                traceback.print_exc()
                llm = LLMDefaultConfig.get_llm_from_config({})

        return llm

    def load_auth(self):
        # Custom auth_handler # TODOAUTH: change the name to custom_auth
        selected_auth_handler = crud.get_setting_by_name(self.id, "auth_handler_selected")

        # if no auth_handler is saved, use default one and save to db
        if selected_auth_handler is None:
            # create the auth settings
            crud.upsert_setting_by_name(
                self.id,
                models.Setting(
                    name="CoreOnlyAuthConfig", category="auth_handler_factory", value={}
                ),
            )
            crud.upsert_setting_by_name(
                self.id,
                models.Setting(
                    name="auth_handler_selected",
                    category="auth_handler_factory",
                    value={"name": "CoreOnlyAuthConfig"},
                ),
            )

            # reload from db
            selected_auth_handler = crud.get_setting_by_name(self.id, "auth_handler_selected")

        # get AuthHandler factory class
        selected_auth_handler_class = selected_auth_handler["value"]["name"]
        factory_class = auth_handlers.get_auth_handler_from_name(selected_auth_handler_class, self.mad_hatter)

        # obtain configuration and instantiate AuthHandler
        selected_auth_handler_config = crud.get_setting_by_name(self.id, selected_auth_handler_class)
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
            self.id,
            models.Setting(name=language_model_name, category="llm_factory", value=settings),
        )

        # general LLM settings are saved in settings table under "llm" category
        crud.upsert_setting_by_name(
            self.id,
            models.Setting(name="llm_selected", category="llm", value={"name": language_model_name}),
        )

        status = {"name": language_model_name, "value": final_setting["value"]}

        # reload the llm of the cat
        self.llm = self.load_language_model()

        # recreate tools embeddings
        self.mad_hatter.find_plugins()

        return status

    @property
    def strays(self):
        return self.__strays

    @property
    def embedder(self) -> EmbedderSettings:
        from cat.bill_the_lizard import BillTheLizard
        return BillTheLizard().embedder

    @property
    def rabbit_hole(self) -> "RabbitHole":
        from cat.bill_the_lizard import BillTheLizard
        return BillTheLizard().rabbit_hole

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
        file_handlers = execute_hook(
            self.mad_hatter, "rabbithole_instantiates_parsers", file_handlers, cat=self
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
        text_splitter = execute_hook(
            self.mad_hatter, "rabbithole_instantiates_splitter", text_splitter, cat=self
        )
        return text_splitter
