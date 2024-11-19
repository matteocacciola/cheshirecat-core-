from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda
from langchain_core.output_parsers.string import StrOutputParser

from cat.agents.base_agent import BaseAgent, AgentOutput
from cat.looking_glass.callbacks import NewTokenHandler, ModelInteractionHandler
from cat import utils


class MemoryAgent(BaseAgent):
    async def execute(self, stray, *args, **kwargs) -> AgentOutput:
        prompt_prefix = kwargs.get("prompt_prefix", "")
        prompt_suffix = kwargs.get("prompt_suffix", "")

        prompt_variables = stray.working_memory.agent_input.model_dump()
        sys_prompt = prompt_prefix + prompt_suffix

        # ensure prompt variables and placeholders match
        prompt_variables, sys_prompt = utils.match_prompt_variables(prompt_variables, sys_prompt)

        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    template=sys_prompt
                ),
                *(stray.working_memory.langchainfy_chat_history()),
            ]
        )

        chain = (
            prompt
            | RunnableLambda(lambda x: utils.langchain_log_prompt(x, "MAIN PROMPT"))
            | stray.cheshire_cat.large_language_model
            | RunnableLambda(lambda x: utils.langchain_log_output(x, "MAIN PROMPT OUTPUT"))
            | StrOutputParser()
        )

        output = chain.invoke(
            # convert to dict before passing to langchain
            prompt_variables,
            config=RunnableConfig(
                callbacks=[NewTokenHandler(stray), ModelInteractionHandler(stray, self.name)]
            )
        )

        return AgentOutput(output=output)
