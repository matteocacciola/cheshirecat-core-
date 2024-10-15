import time
import asyncio
import traceback
from asyncio import AbstractEventLoop
import tiktoken
from typing import Literal, get_args, List, Dict, Any
from langchain.docstore.document import Document
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, BaseMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser
from fastapi import WebSocket
from websockets.exceptions import ConnectionClosedOK

from cat import utils
from cat.bill_the_lizard import BillTheLizard
from cat.agents.base_agent import AgentOutput
from cat.agents.main_agent import MainAgent
from cat.auth.permissions import AuthUserInfo
from cat.convo.messages import CatMessage, UserMessage, MessageWhy, Role, EmbedderModelInteraction
from cat.env import get_env
from cat.factory.embedder import EmbedderSettings
from cat.log import log
from cat.looking_glass.callbacks import NewTokenHandler, ModelInteractionHandler
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.memory.long_term_memory import LongTermMemory
from cat.memory.models import MemoryCollection
from cat.memory.working_memory import WorkingMemory
from cat.rabbit_hole import RabbitHole

MSG_TYPES = Literal["notification", "chat", "error", "chat_token"]


# The Stray cat goes around tools and hook, making troubles
class StrayCat:
    """User/session based object containing working memory and a few utility pointers"""

    def __init__(self, agent_id: str, main_loop: AbstractEventLoop, user_data: AuthUserInfo, ws: WebSocket = None):
        self.__agent_id = agent_id

        self.__user = user_data
        self.working_memory = WorkingMemory(
            **{"agent_id": self.__agent_id, "user_id": self.__user.id}
        )

        # attribute to store ws connection
        self.__ws = ws

        self.__main_loop = main_loop

        self.__loop = asyncio.new_event_loop()
        self.__last_message_time = time.time()

    def __eq__(self, other: "StrayCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, StrayCat):
            return False
        return self.user_id == other.user_id

    def __hash__(self):
        return hash(self.user_id)

    def __repr__(self):
        return f"StrayCat(user_id={self.user_id},agent_id={self.__agent_id})"

    def __send_ws_json(self, data: Any):
        data = data | {"user_id": self.user_id, "agent_id": self.__agent_id}

        # Run the coroutine in the main event loop in the main thread
        # and wait for the result
        asyncio.run_coroutine_threadsafe(self.__ws.send_json(data), loop=self.__main_loop).result()

    def __build_why(self) -> MessageWhy:
        def build_report(memories):
            return [
                dict(d[0]) | {"score": float(d[1]), "id": d[3]}
                for d in memories
            ]

        # build data structure for output (response and why with memories)
        episodic_report = build_report(self.working_memory.episodic_memories)
        declarative_report = build_report(self.working_memory.declarative_memories)
        procedural_report = build_report(self.working_memory.procedural_memories)

        # why this response?
        why = MessageWhy(
            input=self.working_memory.user_message_json.text,
            intermediate_steps=[],
            memory={
                str(MemoryCollection.EPISODIC): episodic_report,
                str(MemoryCollection.DECLARATIVE): declarative_report,
                str(MemoryCollection.PROCEDURAL): procedural_report,
            },
            model_interactions=self.working_memory.model_interactions,
        )

        return why

    def send_ws_message(self, content: str, msg_type: MSG_TYPES = "notification"):
        """Send a message via websocket.

        This method is useful for sending a message via websocket directly without passing through the LLM
        In case there is no connection the message is skipped and a warning is logged

        Parameters
        ----------
        content : str
            The content of the message.
        msg_type : str
            The type of the message. Should be either `notification`, `chat`, `chat_token` or `error`
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.user_id}")
            return

        options = get_args(MSG_TYPES)

        if msg_type not in options:
            raise ValueError(
                f"The message type `{msg_type}` is not valid. Valid types: {', '.join(options)}"
            )

        if msg_type == "error":
            self.__send_ws_json(
                {"type": msg_type, "name": "GenericError", "description": str(content)}
            )
        else:
            self.__send_ws_json({"type": msg_type, "content": content})

    def send_chat_message(self, message: str | CatMessage, save=False):
        """Sends a chat message to the user using the active WebSocket connection.

        In case there is no connection the message is skipped and a warning is logged

        Args:
            message (Union[str, CatMessage]): message to send
            save (bool, optional): Save the message in the conversation history. Defaults to False.
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.user_id}")
            return

        if isinstance(message, str):
            why = self.__build_why()
            message = CatMessage(content=message, user_id=self.user_id, why=why)

        if save:
            self.working_memory.update_conversation_history(
                who=Role.AI, message=message["content"], why=message.why
            )

        self.__send_ws_json(message.model_dump())

    def send_notification(self, content: str):
        """Sends a notification message to the user using the active WebSocket connection.

        In case there is no connection the message is skipped and a warning is logged

        Args:
            content (str): message to send
        """

        self.send_ws_message(content=content, msg_type="notification")

    def send_error(self, error: str | Exception):
        """Sends an error message to the user using the active WebSocket connection.

        In case there is no connection the message is skipped and a warning is logged

        Args:
            error (Union[str, Exception]): message to send
        """

        if self.__ws is None:
            log.warning(f"No websocket connection is open for user {self.user_id}")
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

        self.__send_ws_json(error_message)

    def recall_relevant_memories_to_working_memory(self, query=None):
        """Retrieve context from memory.

        The method retrieves the relevant memories from the vector collections that are given as context to the LLM.
        Recalled memories are stored in the working memory.

        Parameters
        ----------
        query : str, optional
        The query used to make a similarity search in the Cat's vector memories. If not provided, the query
        will be derived from the user's message.

        Notes
        -----
        The user's message is used as a query to make a similarity search in the Cat's vector memories.
        Five hooks allow to customize the recall pipeline before and after it is done.

        See Also
        --------
        cat_recall_query
        before_cat_recalls_memories
        before_cat_recalls_episodic_memories
        before_cat_recalls_declarative_memories
        before_cat_recalls_procedural_memories
        after_cat_recalls_memories
        """
        cheshire_cat = self.cheshire_cat

        # If query is not provided, use the user's message as the query
        recall_query = query if query is not None else self.working_memory.user_message_json.text

        # We may want to search in memory
        mad_hatter = cheshire_cat.mad_hatter
        recall_query = mad_hatter.execute_hook(
            "cat_recall_query", recall_query, cat=self
        )
        log.info(f"Recall query: '{recall_query}'")

        # Embed recall query
        recall_query_embedding = cheshire_cat.embedder.embed_query(recall_query)
        self.working_memory.recall_query = recall_query
        
        # keep track of embedder model usage
        self.working_memory.model_interactions.append(
            EmbedderModelInteraction(
                prompt=recall_query,
                reply=recall_query_embedding,
                input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(recall_query)),
            )
        )

        # hook to do something before recall begins
        mad_hatter.execute_hook("before_cat_recalls_memories", cat=self)

        # Setting default recall configs for each memory
        # TODO: can these data structures become instances of a RecallSettings class?
        default_episodic_recall_config = {
            "embedding": recall_query_embedding,
            "k": 3,
            "threshold": 0.7,
            "metadata": {"source": self.user_id},
        }

        default_declarative_recall_config = {
            "embedding": recall_query_embedding,
            "k": 3,
            "threshold": 0.7,
            "metadata": None,
        }

        default_procedural_recall_config = {
            "embedding": recall_query_embedding,
            "k": 3,
            "threshold": 0.7,
            "metadata": None,
        }

        # hooks to change recall configs for each memory
        recall_configs = [
            mad_hatter.execute_hook(
                "before_cat_recalls_episodic_memories",
                default_episodic_recall_config,
                cat=self,
            ),
            mad_hatter.execute_hook(
                "before_cat_recalls_declarative_memories",
                default_declarative_recall_config,
                cat=self,
            ),
            mad_hatter.execute_hook(
                "before_cat_recalls_procedural_memories",
                default_procedural_recall_config,
                cat=self,
            ),
        ]

        memory_types = cheshire_cat.memory.vectors.collections.keys()

        for config, memory_type in zip(recall_configs, memory_types):
            memory_key = f"{memory_type}_memories"

            # recall relevant memories for collection
            vector_memory = getattr(cheshire_cat.memory.vectors, memory_type)
            memories = vector_memory.recall_memories_from_embedding(**config)

            setattr(
                self.working_memory, memory_key, memories
            )  # self.working_memory.procedural_memories = ...

        # hook to modify/enrich retrieved memories
        mad_hatter.execute_hook("after_cat_recalls_memories", cat=self)

    def llm_response(self, prompt: str, stream: bool = False) -> str:
        """Generate a response using the LLM model.

        This method is useful for generating a response with both a chat and a completion model using the same syntax

        Parameters
        ----------
        prompt : str
            The prompt for generating the response.
        stream : bool, optional
            Whether to stream the tokens or not.

        Returns
        -------
        str
            The generated response.

        """

        # should we stream the tokens?
        callbacks = []
        if stream:
            callbacks.append(NewTokenHandler(self))

        # Add a token counter to the callbacks
        caller = utils.get_caller_info()
        callbacks.append(ModelInteractionHandler(self, caller or "StrayCat"))

        # here we deal with motherfucking langchain
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessage(content=prompt)
                # TODO: add here optional convo history passed to the method, 
                #  or taken from working memory
            ]
        )

        chain = (
            prompt
            | RunnableLambda(lambda x: utils.langchain_log_prompt(x, f"{caller} prompt"))
            | self.cheshire_cat.llm
            | RunnableLambda(lambda x: utils.langchain_log_output(x, f"{caller} prompt output"))
            | StrOutputParser()
        )

        output = chain.invoke(
            {}, # in case we need to pass info to the template
            config=RunnableConfig(callbacks=callbacks)
        )

        return output

    async def __call__(self, message_dict: Dict) -> Dict:
        """Call the Cat instance.

        This method is called on the user's message received from the client.

        Parameters
        ----------
        message_dict : Dict
            Dictionary received from the Websocket client.

        Returns
        -------
        final_output : Dict
            Dictionary with the Cat's answer to be sent to the client.

        Notes
        -----
        Here happens the main pipeline of the Cat. Namely, the Cat receives the user's input and recall the memories.
        The retrieved context is formatted properly and given in input to the Agent that uses the LLM to produce the
        answer. This is formatted in a dictionary to be sent as a JSON via Websocket to the client.

        """

        # Parse websocket message into UserMessage obj
        user_message = UserMessage.model_validate(message_dict)
        log.info(user_message)

        # set a few easy access variables
        self.working_memory.user_message_json = user_message

        # keeping track of model interactions
        self.working_memory.model_interactions = []

        # hook to modify/enrich user input
        cheshire_cat = self.cheshire_cat
        mad_hatter = cheshire_cat.mad_hatter
        self.working_memory.user_message_json = mad_hatter.execute_hook(
            "before_cat_reads_message", self.working_memory.user_message_json, cat=self
        )

        # text of latest Human message
        user_message_text = self.working_memory.user_message_json.text

        # update conversation history (Human turn)
        self.working_memory.update_conversation_history(who=Role.HUMAN, message=user_message_text)

        # recall episodic and declarative memories from vector collections
        #   and store them in working_memory
        try:
            self.recall_relevant_memories_to_working_memory()
        except Exception as e:
            log.error(e)
            traceback.print_exc()

            err_message = "An error occurred while recalling relevant memories."

            return {
                "type": "error",
                "name": "VectorMemoryError",
                "description": err_message,
            }

        # reply with agent
        try:
            agent_output: AgentOutput = await self.main_agent.execute(self)
        except Exception as e:
            # This error happens when the LLM
            #   does not respect prompt instructions.
            # We grab the LLM output here anyway, so small and
            #   non instruction-fine-tuned models can still be used.
            error_description = str(e)

            log.error(error_description)
            if "Could not parse LLM output: `" not in error_description:
                raise e

            unparsable_llm_output = error_description.replace(
                "Could not parse LLM output: `", ""
            ).replace("`", "")
            agent_output = AgentOutput(
                output=unparsable_llm_output,
            )

        log.info("Agent output returned to stray:")
        log.info(agent_output)

        doc = Document(
            page_content=user_message_text,
            metadata={"source": self.user_id, "when": time.time()},
        )
        doc = mad_hatter.execute_hook(
            "before_cat_stores_episodic_memory", doc, cat=self
        )
        # store user message in episodic memory
        # TODO: vectorize and store also conversation chunks
        #   (not raw dialog, but summarization)
        user_message_embedding = cheshire_cat.embedder.embed_documents([user_message_text])
        _ = cheshire_cat.memory.vectors.episodic.add_point(
            doc.page_content,
            user_message_embedding[0],
            doc.metadata,
        )

        # why this response?
        why = self.__build_why()
        # TODO: should these assignations be included in self.__build_why ?
        why.intermediate_steps = agent_output.intermediate_steps
        why.agent_output = agent_output.model_dump()

        # prepare final cat message
        final_output = CatMessage(
            user_id=self.user_id, content=str(agent_output.output), why=why
        )

        # run message through plugins
        final_output = mad_hatter.execute_hook(
            "before_cat_sends_message", final_output, cat=self
        )

        # update conversation history (AI turn)
        self.working_memory.update_conversation_history(
            who=Role.AI, message=final_output.content, why=final_output.why
        )

        self.__last_message_time = time.time()

        return final_output

    def run(self, user_message_json, return_message: bool | None = False):
        try:
            cat_message = self.loop.run_until_complete(self.__call__(user_message_json))
            if return_message:
                # return the message for HTTP usage
                return cat_message

            # send message back to client via WS
            self.send_chat_message(cat_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(e)
            traceback.print_exc()
            if return_message:
                return {"error": str(e)}
            try:
                # Send error as websocket message
                self.send_error(e)
            except ConnectionClosedOK as ex:
                log.warning(ex)
                self.nullify_connection()

    def classify(self, sentence: str, labels: List[str] | Dict[str, List[str]]) -> str | None:
        """Classify a sentence.

        Parameters
        ----------
        sentence : str
            Sentence to be classified.
        labels : List[str] or Dict[str, List[str]]
            Possible output categories and optional examples.

        Returns
        -------
        label : str
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
            for label, examples in labels.items():
                for ex in examples:
                    examples_list += f'\n"{ex}" -> "{label}"'
        else:
            labels_names = labels
            examples_list = ""

        labels_list = '"' + '", "'.join(labels_names) + '"'

        prompt = f"""Classify this sentence:
"{sentence}"

Allowed classes are:
{labels_list}{examples_list}

"{sentence}" -> """

        response = self.llm_response(prompt)
        log.info(response)

        # find the closest match and its score with levenshtein distance
        best_label, score = min(
            ((label, utils.levenshtein_distance(response, label)) for label in labels_names),
            key=lambda x: x[1],
        )

        # set 0.5 as threshold - let's see if it works properly
        return best_label if score < 0.5 else None

    def stringify_chat_history(self, latest_n: int = 5) -> str:
        """Serialize chat history.
        Converts to text the recent conversation turns.

        Args:
            latest_n (int. optional): How many latest turns to stringify. Defaults to 5.

        Returns
            str: String with recent conversation turns.

        Notes
        -----
        Such context is placed in the `agent_prompt_suffix` in the place held by {chat_history}.

        The chat history is a dictionary with keys::
            'who': the name of who said the utterance;
            'message': the utterance.
        """

        history = self.working_memory.get_conversation_history()[-latest_n:]
        history = [h.model_dump() for h in history]

        history_strings = [f"\n - {str(turn['who'])}: {turn['message']}" for turn in history]
        return "".join(history_strings)

    def langchainfy_chat_history(self, latest_n: int = 5) -> List[BaseMessage]:
        """Get the chat history in Langchain format.

        Args:
            latest_n (int, optional): Number of latest messages to get. Defaults to 5.

        Returns:
            List[BaseMessage]: List of Langchain messages.
        """

        chat_history = self.working_memory.get_conversation_history()[-latest_n:]
        chat_history = [ch.model_dump() for ch in chat_history]

        langchain_chat_history = [
            HumanMessage(name=str(message["who"]), content=message["message"])
            if message["role"] == Role.HUMAN else AIMessage(name=str(message["who"]), content=message["message"])
            for message in chat_history
        ]

        return langchain_chat_history

    async def close_connection(self):
        if not self.__ws:
            return
        try:
            await self.__ws.close()
        except RuntimeError as ex:
            log.warning(ex)
            self.nullify_connection()

    def nullify_connection(self):
        self.__ws = None

    def reset_connection(self, connection):
        """Reset the connection to the API service."""
        self.__ws = connection

    @property
    def user_id(self) -> str:
        return self.__user.id

    @property
    def agent_id(self) -> str:
        return self.__agent_id

    @property
    def cheshire_cat(self):
        ccat = BillTheLizard().get_cheshire_cat(self.__agent_id)
        if not ccat:
            raise ValueError(f"Cheshire Cat not found for the StrayCat {self.user_id}.")

        return ccat

    @property
    def llm(self) -> BaseLanguageModel:
        return self.cheshire_cat.llm

    @property
    def embedder(self) -> EmbedderSettings:
        return BillTheLizard().embedder

    @property
    def memory(self) -> LongTermMemory:
        return self.cheshire_cat.memory

    @property
    def rabbit_hole(self) -> RabbitHole:
        return BillTheLizard().rabbit_hole

    @property
    def mad_hatter(self) -> MadHatter:
        return self.cheshire_cat.mad_hatter

    @property
    def main_agent(self) -> MainAgent:
        return BillTheLizard().main_agent

    @property
    def white_rabbit(self) -> WhiteRabbit:
        return BillTheLizard().white_rabbit

    @property
    def loop(self):
        return self.__loop

    @property
    def is_idle(self) -> bool:
        return time.time() - self.__last_message_time >= float(get_env("CCAT_STRAYCAT_TIMEOUT"))
