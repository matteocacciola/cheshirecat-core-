import time
import asyncio
import traceback
import tiktoken
from typing import Literal, List, Dict, Any, get_args
from langchain.docstore.document import Document
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from langchain_core.runnables import RunnableConfig
from fastapi import WebSocket
from websockets.exceptions import ConnectionClosedOK

from cat import utils
from cat.agents.base_agent import AgentOutput
from cat.agents.main_agent import MainAgent
from cat.auth.permissions import AuthUserInfo
from cat.convo.messages import EmbedderModelInteraction, CatMessage, Role, MessageWhy, UserMessage
from cat.env import get_env
from cat.exceptions import VectorMemoryError
from cat.log import log
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.callbacks import NewTokenHandler, ModelInteractionHandler
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.tweedledee import Tweedledee
from cat.memory.long_term_memory import LongTermMemory
from cat.memory.vector_memory_collection import VectorMemoryCollectionTypes, DocumentRecall, VectorMemoryCollection
from cat.memory.working_memory import WorkingMemory
from cat.rabbit_hole import RabbitHole

MSG_TYPES = Literal["notification", "chat", "error", "chat_token"]
DEFAULT_K = 3
DEFAULT_THRESHOLD = 0.5


class RecallSettings(utils.BaseModelDict):
    embedding: List[float]
    k: float | None = DEFAULT_K
    threshold: float | None = DEFAULT_THRESHOLD
    metadata: dict | None = None


# The Stray cat goes around tools and hook, making troubles
class StrayCat:
    """User/session based object containing working memory and a few utility pointers"""

    def __init__(self, agent_id: str, user_data: AuthUserInfo, ws: WebSocket = None):
        self.__agent_id = agent_id

        self.__user = user_data
        self.working_memory = WorkingMemory(agent_id=self.__agent_id, user_id=self.__user.id)

        # attribute to store ws connection
        self.__ws = ws

        self.__main_loop = self.__get_main_loop()
        self.__last_message_time = time.time()

    def __eq__(self, other: "StrayCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, StrayCat):
            return False
        return self.__user.id == other.user.id

    def __hash__(self):
        return hash(self.__user.id)

    def __repr__(self):
        return f"StrayCat(user_id={self.__user.id}, agent_id={self.__agent_id})"

    def __get_main_loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.get_event_loop()

    def _send_ws_json(self, data: Any):
        # Run the coroutine in the main event loop in the main thread
        # and wait for the result
        asyncio.run_coroutine_threadsafe(self.__ws.send_json(data), loop=self.__main_loop).result()

    def _build_why(self, agent_output: AgentOutput | None = None) -> MessageWhy:
        memory = {str(c): [dict(d.document) | {
            "score": float(d.score) if d.score else None,
            "id": d.id,
        } for d in getattr(self.working_memory, f"{c}_memories")] for c in VectorMemoryCollectionTypes}

        # why this response?
        return MessageWhy(
            input=self.working_memory.user_message.text,
            intermediate_steps=agent_output.intermediate_steps if agent_output else [],
            memory=memory,
            model_interactions=self.working_memory.model_interactions,
            agent_output=agent_output.model_dump() if agent_output else None
        )

    def send_ws_message(self, content: str, msg_type: MSG_TYPES = "notification"):
        """
        Send a message via websocket.
        This method is useful for sending a message via websocket directly without passing through the LLM
        In case there is no connection the message is skipped and a warning is logged

        Args:
            content: str
                The content of the message.
            msg_type: str
                The type of the message. Should be either `notification`, `chat`, `chat_token` or `error`
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.__user.id}")
            return

        options = get_args(MSG_TYPES)

        if msg_type not in options:
            raise ValueError(
                f"The message type `{msg_type}` is not valid. Valid types: {', '.join(options)}"
            )

        if msg_type == "error":
            self._send_ws_json(
                {"type": msg_type, "name": "GenericError", "description": str(content)}
            )
            return
        self._send_ws_json({"type": msg_type, "content": content})

    def send_chat_message(self, message: str | CatMessage, save=False):
        """
        Sends a chat message to the user using the active WebSocket connection.
        In case there is no connection the message is skipped and a warning is logged.

        Args:
            message (str | CatMessage): message to send
            save (bool, optional): Save the message in the conversation history. Defaults to False.
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.__user.id}")
            return

        if isinstance(message, str):
            message = CatMessage(text=message, why=self._build_why())

        if save:
            self.working_memory.update_history(who=Role.AI, content=message)

        self._send_ws_json(message.model_dump())

    def send_notification(self, content: str):
        """
        Sends a notification message to the user using the active WebSocket connection.
        In case there is no connection the message is skipped and a warning is logged.

        Args:
            content (str): message to send
        """

        self.send_ws_message(content=content, msg_type="notification")

    def send_error(self, error: str | Exception):
        """
        Sends an error message to the user using the active WebSocket connection.
        In case there is no connection the message is skipped and a warning is logged.

        Args:
            error (Union[str, Exception]): message to send
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.__user.id}")
            return

        if isinstance(error, str):
            error_message = {
                "type": "error",
                "name": "GenericError",
                "description": str(error),
            }
        else:
            error_message = {
                "type": "error",
                "name": error.__class__.__name__,
                "description": str(error),
            }

        self._send_ws_json(error_message)

    def recall(
        self,
        query: List[float],
        collection_name: str,
        k: int | None = 5,
        threshold: int | None = None,
        metadata: Dict | None = None,
    ) -> List[DocumentRecall]:
        """
        This is a proxy method to perform search in a vector memory collection.
        The method allows retrieving information from one specific vector memory collection with custom parameters.
        The Cat uses this method internally.
        to recall the relevant memories to Working Memory every user's chat interaction.
        This method is useful also to perform a manual search in hook and tools.

        Args:
            query: List[float]
                The search query, passed as embedding vector.
                Please, first run cheshire_cat.embedder.embed_query(query) if you have a string query to pass here.
            collection_name: str
                The name of the collection to perform the search.
                Available collections are: *episodic*, *declarative*, *procedural*.
            k: int | None
                The number of memories to retrieve.
                If `None` retrieves all the available memories.
            threshold: float | None
                The minimum similarity to retrieve a memory.
                Memories with lower similarity are ignored.
            metadata: Dict
                Additional filter to retrieve memories with specific metadata.

        Returns:
            memories: List[DocumentRecall]
                List of retrieved memories.

        See Also:
            VectorMemoryCollection.recall_memories_from_embedding
            VectorMemoryCollection.recall_all_memories
        """

        cheshire_cat = self.cheshire_cat

        if collection_name not in VectorMemoryCollectionTypes:
            memory_collections = ', '.join([str(c) for c in VectorMemoryCollectionTypes])
            error_message = f"{collection_name} is not a valid collection. Available collections: {memory_collections}"

            log.error(error_message)
            raise ValueError(error_message)

        vector_memory: VectorMemoryCollection = cheshire_cat.memory.vectors.collections[collection_name]

        memories = vector_memory.recall_memories_from_embedding(
            query, metadata, k, threshold
        ) if k else vector_memory.recall_all_memories()

        setattr(self.working_memory, f"{collection_name}_memories", memories)

        return memories

    def recall_relevant_memories_to_working_memory(self, query: str | None = None):
        """
        Retrieve context from memory.
        The method retrieves the relevant memories from the vector collections that are given as context to the LLM.
        Recalled memories are stored in the working memory.

        Args:
            query: str, optional
                The query used to make a similarity search in the Cat's vector memories. If not provided, the query
                will be derived from the user's message.

        See Also:
            cat_recall_query
            before_cat_recalls_memories
            before_cat_recalls_episodic_memories
            before_cat_recalls_declarative_memories
            before_cat_recalls_procedural_memories
            after_cat_recalls_memories

        Notes
        -----
        The user's message is used as a query to make a similarity search in the Cat's vector memories.
        Five hooks allow to customize the recall pipeline before and after it is done.
        """
        cheshire_cat = self.cheshire_cat
        plugin_manager = self.plugin_manager

        # We may want to search in memory. If query is not provided, use the user's message as the query
        recall_query = plugin_manager.execute_hook(
            "cat_recall_query",
            query if query is not None else self.working_memory.user_message.text,
            cat=self
        )
        log.info(f"Agent id: {self.__agent_id}. Recall query: '{recall_query}'")

        # Embed recall query
        recall_query_embedding = cheshire_cat.embedder.embed_query(recall_query)

        # keep track of embedder model usage
        self.working_memory.recall_query = recall_query
        self.working_memory.model_interactions.append(
            EmbedderModelInteraction(
                prompt=recall_query,
                reply=recall_query_embedding,
                input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(recall_query)),
            )
        )

        # hook to do something before recall begins
        plugin_manager.execute_hook("before_cat_recalls_memories", cat=self)

        # Setting default recall configs for each memory + hooks to change recall configs for each memory
        for memory_type in VectorMemoryCollectionTypes:
            metadata = {"source": self.__user.id} if memory_type == VectorMemoryCollectionTypes.EPISODIC else None
            config = utils.restore_original_model(
                plugin_manager.execute_hook(
                    f"before_cat_recalls_{str(memory_type)}_memories",
                    RecallSettings(embedding=recall_query_embedding, metadata=metadata),
                    cat=self,
                ),
                RecallSettings,
            )

            self.recall(
                query=config.embedding,
                collection_name=str(memory_type),
                k=config.k,
                threshold=config.threshold,
                metadata=config.metadata,
            )

        # hook to modify/enrich retrieved memories
        plugin_manager.execute_hook("after_cat_recalls_memories", cat=self)

    def llm(self, prompt: str, stream: bool = False) -> str:
        """
        Generate a response using the LLM model.
        This method is useful for generating a response with both a chat and a completion model using the same syntax.

        Args:
            prompt: str
                The prompt for generating the response.
            stream: bool, optional
                Whether to stream the tokens or not.

        Returns: The generated response.
        """

        # should we stream the tokens?
        callbacks = [] if not stream else NewTokenHandler(self)

        # Add a token counter to the callbacks
        caller = utils.get_caller_info()
        callbacks.append(ModelInteractionHandler(self, caller or "StrayCat"))

        return self.cheshire_cat.llm(prompt, caller=caller, config=RunnableConfig(callbacks=callbacks))

    def __call__(self, user_message: UserMessage) -> CatMessage:
        """
        Call the Cat instance.
        This method is called on the user's message received from the client.

        Args:
            user_message: UserMessage
                Message received from the Websocket client.

        Returns:
            final_output: CatMessage
                Cat Message object, the Cat's answer to be sent to the client.

        Notes
        -----
        Here happens the main pipeline of the Cat. Namely, the Cat receives the user's input and recalls the memories.
        The retrieved context is formatted properly and given in input to the Agent that uses the LLM to produce the
        answer. This is formatted in a dictionary to be sent as a JSON via Websocket to the client.
        """

        ### setup working memory
        # keeping track of model interactions
        self.working_memory.model_interactions = []
        # latest user message
        self.working_memory.user_message = user_message

        plugin_manager = self.plugin_manager

        # Run a totally custom reply (skips all the side effects of the framework)
        fast_reply = plugin_manager.execute_hook("fast_reply", {}, cat=self)
        fast_reply["text"] = fast_reply.get("output", "")
        fast_reply = utils.restore_original_model(fast_reply, CatMessage)
        if fast_reply and fast_reply.text:
            return fast_reply

        # hook to modify/enrich user input; this is the latest Human message
        self.working_memory.user_message = utils.restore_original_model(
            plugin_manager.execute_hook("before_cat_reads_message", self.working_memory.user_message, cat=self),
            UserMessage
        )

        # update conversation history (Human turn)
        self.working_memory.update_history(who=Role.HUMAN, content=self.working_memory.user_message)

        # recall episodic and declarative memories from vector collections and store them in working_memory
        try:
            self.recall_relevant_memories_to_working_memory()
        except Exception as e:
            log.error(f"Agent id: {self.__agent_id}. Error {e}")
            traceback.print_exc()

            raise VectorMemoryError("An error occurred while recalling relevant memories.")

        agent_output = self._build_agent_output()
        log.info(f"Agent id: {self.__agent_id}. Agent output returned to stray:")
        log.info(agent_output)

        return self._on_agent_output_built(agent_output)

    def run_http(self, user_message: UserMessage) -> CatMessage:
        try:
            return self.__call__(user_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.__agent_id}. Error {e}")
            traceback.print_exc()
            return CatMessage(text="", error=str(e))

    def run_websocket(self, user_message: UserMessage) -> None:
        try:
            cat_message = self.__call__(user_message)
            # send message back to client via WS
            self.send_chat_message(cat_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.__agent_id}. Error {e}")
            traceback.print_exc()
            try:
                # Send error as websocket message
                self.send_error(e)
            except ConnectionClosedOK as ex:
                log.warning(f"Agent id: {self.__agent_id}. Warning {ex}")
                # self.nullify_connection()

    def classify(self, sentence: str, labels: List[str] | Dict[str, List[str]]) -> str | None:
        """
        Classify a sentence.

        Args:
            sentence: str
                Sentence to be classified.
            labels: List[str] or Dict[str, List[str]]
                Possible output categories and optional examples.

        Returns:
            label: str
                Sentence category.

        Examples
        -------
        >>> cat.classify("I feel good", labels=["positive", "negative"])
        "positive"

        Or giving examples for each category:

        >>> example_labels = {
        ...     "positive": ["I feel nice", "happy today"],
        ...     "negative": ["I feel bad", "not my best day"],
        ... }
        ... cat.classify("it is a bad day", labels=example_labels)
        "negative"
        """

        if isinstance(labels, Dict):
            labels_names = labels.keys()
            examples_list = "\n\nExamples:"
            examples_list += "".join([
                f'\n"{ex}" -> "{label}"' for label, examples in labels.items() for ex in examples
            ])
        else:
            labels_names = labels
            examples_list = ""

        labels_list = '"' + '", "'.join(labels_names) + '"'

        prompt = f"""Classify this sentence:
"{sentence}"

Allowed classes are:
{labels_list}{examples_list}

"{sentence}" -> """

        response = self.llm(prompt)
        log.info(response)

        # find the closest match and its score with levenshtein distance
        best_label, score = min(
            ((label, utils.levenshtein_distance(response, label)) for label in labels_names),
            key=lambda x: x[1],
        )

        # set 0.5 as threshold - let's see if it works properly
        return best_label if score < 0.5 else None

    async def close_connection(self):
        if not self.__ws:
            return
        try:
            await self.__ws.close()
        except RuntimeError as ex:
            log.warning(f"Agent id: {self.__agent_id}. Warning {ex}")
            self.nullify_connection()

    def nullify_connection(self):
        self.__ws = None

    def reset_connection(self, connection):
        """Reset the connection to the API service."""
        self.__ws = connection

    def _build_agent_output(self) -> AgentOutput:
        # reply with agent
        try:
            agent_output: AgentOutput = self.main_agent.execute(self)
            if agent_output.output == utils.default_llm_answer_prompt():
                agent_output.with_llm_error = True
        except Exception as e:
            # This error happens when the LLM does not respect prompt instructions.
            # We grab the LLM output here anyway, so small and non instruction-fine-tuned models can still be used.
            error_description = str(e)

            log.error(f"Agent id: {self.__agent_id}. Error: {error_description}")
            if "Could not parse LLM output: `" not in error_description:
                raise e

            unparsable_llm_output = error_description.replace(
                "Could not parse LLM output: `", ""
            ).replace("`", "")
            agent_output = AgentOutput(output=unparsable_llm_output, with_llm_error=True)

        return agent_output

    def _on_agent_output_built(self, agent_output: AgentOutput) -> CatMessage:
        if not agent_output.with_llm_error:
            self._store_user_message_in_episodic_memory(self.working_memory.user_message)

        # prepare final cat message
        final_output = CatMessage(text=str(agent_output.output), why=self._build_why(agent_output))

        # run message through plugins
        final_output = utils.restore_original_model(
            self.plugin_manager.execute_hook("before_cat_sends_message", final_output, cat=self),
            CatMessage,
        )

        # update conversation history (AI turn)
        if agent_output.with_llm_error:
            self.working_memory.pop_last_message_if_human()
        else:
            self.working_memory.update_history(who=Role.AI, content=final_output)

        self.__last_message_time = time.time()

        return final_output

    def _store_user_message_in_episodic_memory(self, user_message: UserMessage):
        doc = Document(
            page_content=user_message.text,
            metadata={"source": self.__user.id, "when": time.time()},
        )
        doc = self.plugin_manager.execute_hook(
            "before_cat_stores_episodic_memory", doc, cat=self
        )
        # store user message in episodic memory
        # TODO: vectorize and store also conversation chunks (not raw dialog, but summarization)
        cheshire_cat = self.cheshire_cat
        user_message_embedding = cheshire_cat.embedder.embed_documents([user_message.text])
        cheshire_cat.memory.vectors.episodic.add_point(
            doc.page_content,
            user_message_embedding[0],
            doc.metadata,
        )

    async def shutdown(self):
        await self.close_connection()

    @property
    def user(self) -> AuthUserInfo:
        return self.__user

    @property
    def agent_id(self) -> str:
        return self.__agent_id

    @property
    def lizard(self) -> BillTheLizard:
        return BillTheLizard()

    @property
    def cheshire_cat(self) -> "CheshireCat":
        ccat = self.lizard.get_cheshire_cat(self.__agent_id)
        if not ccat:
            raise ValueError(f"Cheshire Cat not found for the StrayCat {self.__user.id}.")

        return ccat

    @property
    def large_language_model(self) -> BaseLanguageModel:
        return self.cheshire_cat.large_language_model

    @property
    def _llm(self) -> BaseLanguageModel:
        return self.large_language_model

    @property
    def embedder(self) -> Embeddings:
        return self.lizard.embedder

    @property
    def memory(self) -> LongTermMemory:
        return self.cheshire_cat.memory

    @property
    def rabbit_hole(self) -> RabbitHole:
        return self.lizard.rabbit_hole

    @property
    def plugin_manager(self) -> Tweedledee:
        return self.cheshire_cat.plugin_manager

    @property
    def mad_hatter(self) -> Tweedledee:
        return self.cheshire_cat.plugin_manager

    @property
    def main_agent(self) -> MainAgent:
        return self.lizard.main_agent

    @property
    def white_rabbit(self) -> WhiteRabbit:
        return WhiteRabbit()

    @property
    def is_idle(self) -> bool:
        return time.time() - self.__last_message_time >= float(get_env("CCAT_STRAYCAT_TIMEOUT"))

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        return self.cheshire_cat.file_handlers

    # each time we access the text splitter, plugins can intervene
    @property
    def text_splitter(self):
        return self.cheshire_cat.text_splitter
