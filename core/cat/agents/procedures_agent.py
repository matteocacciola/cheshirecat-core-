import traceback
import random
from typing import Dict, Any
from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda

from cat.agents.base_agent import BaseAgent, AgentOutput
from cat.agents.form_agent import FormAgent
from cat.looking_glass import prompts
from cat.looking_glass.output_parser import ChooseProcedureOutputParser, LLMAction
from cat.experimental.form.cat_form import CatForm
from cat.mad_hatter.decorators.tool import CatTool
from cat.mad_hatter.plugin import Plugin
from cat.log import log
from cat.looking_glass.callbacks import ModelInteractionHandler
from cat import utils


class ProceduresAgent(BaseAgent):
    form_agent = FormAgent()
    allowed_procedures: Dict[str, CatTool | CatForm] = {}

    async def execute(self, stray, *args, **kwargs) -> AgentOutput:
        # Run active form if present
        form_output: AgentOutput = await self.form_agent.execute(stray)
        if form_output.return_direct:
            return form_output
        
        # Select and run useful procedures
        procedural_memories = stray.working_memory.procedural_memories
        if len(procedural_memories) > 0:
            log.debug(f"Procedural memories retrieved: {len(procedural_memories)}.")

            try:
                procedures_result = await self.execute_procedures(stray)
                if procedures_result.return_direct:
                    # exit agent if a return_direct procedure was executed
                    return procedures_result

                # store intermediate steps to enrich memory chain
                intermediate_steps = procedures_result.intermediate_steps

                # Adding the tools_output key in agent input, needed by the memory chain
                if len(intermediate_steps) > 0:
                    stray.working_memory.agent_input.tools_output = "## Context of executed system tools: \n"
                    stray.working_memory.agent_input.tools_output += " - ".join([
                        f"{proc_res[0][0]}: {proc_res[1]}\n" for proc_res in intermediate_steps
                    ])
                return procedures_result
            except Exception as e:
                log.error(e)
                traceback.print_exc()

        return AgentOutput()

    async def execute_procedures(self, stray) -> AgentOutput:
        """
        Execute procedures.
        Args:
            stray: StrayCat instance

        Returns:
            AgentOutput instance
        """

        mad_hatter = stray.cheshire_cat.mad_hatter

        # get procedures prompt from plugins
        procedures_prompt_template = mad_hatter.execute_hook(
            "agent_prompt_instructions", prompts.TOOL_PROMPT, cat=stray
        )

        # Gather recalled procedures
        recalled_procedures_names = {
            p[0].metadata["source"] for p in stray.working_memory.procedural_memories if
            p[0].metadata["type"] in ["tool", "form"] and p[0].metadata["trigger_type"] in [
                "description", "start_example"
            ]
        }
        recalled_procedures_names = mad_hatter.execute_hook(
            "agent_allowed_tools", recalled_procedures_names, cat=stray
        )

        # Prepare allowed procedures (tools instances and form classes)
        allowed_procedures = {p.name: p for p in mad_hatter.procedures if p.name in recalled_procedures_names}

        # Execute chain and obtain a choice of procedure from the LLM
        llm_action = await self.execute_chain(stray, procedures_prompt_template, allowed_procedures)

        # route execution to subagents
        return await self.execute_subagents(stray, llm_action, allowed_procedures)

    async def execute_chain(
        self, stray, procedures_prompt_template: Any, allowed_procedures: Dict[str, CatTool | CatForm]
    ) -> LLMAction:
        """
        Execute the chain to choose a procedure.
        Args:
            stray: StrayCat instance
            procedures_prompt_template: Any
            allowed_procedures: Dict[str, CatTool | CatForm]

        Returns:
            LLMAction instance
        """

        # Prepare info to fill up the prompt
        prompt_variables = {
            "tools": "\n".join(
                f'- "{tool.name}": {tool.description}'
                for tool in allowed_procedures.values()
            ),
            "tool_names": '"' + '", "'.join(allowed_procedures.keys()) + '"',
            #"chat_history": stray.stringify_chat_history(),
            "examples": self.generate_examples(allowed_procedures),
        }

        # Ensure prompt inputs and prompt placeholders map
        prompt_variables, procedures_prompt_template = utils.match_prompt_variables(
            prompt_variables, procedures_prompt_template
        )

        # Generate prompt
        prompt = ChatPromptTemplate(
            messages=[
                SystemMessagePromptTemplate.from_template(
                    template=procedures_prompt_template
                ),
                *(stray.langchainfy_chat_history()),
            ]
        )

        chain = (
            prompt
            | RunnableLambda(lambda x: utils.langchain_log_prompt(x, "TOOL PROMPT"))
            | stray.cheshire_cat.llm
            | RunnableLambda(lambda x: utils.langchain_log_output(x, "TOOL PROMPT OUTPUT"))
            | ChooseProcedureOutputParser() # ensures output is a LLMAction
        )

        llm_action: LLMAction = chain.invoke(
            prompt_variables,
            config=RunnableConfig(callbacks=[ModelInteractionHandler(stray, self.__class__.__name__)])
        )

        return llm_action
    
    async def execute_subagents(
        self, stray, llm_action: LLMAction, allowed_procedures: Dict[str, CatTool | CatForm]
    ) -> AgentOutput:
        """
        Execute subagents.
        Args:
            stray: StrayCat instance
            llm_action: LLMAction instance
            allowed_procedures: Dict[str, CatTool | CatForm]

        Returns:
            AgentOutput instance
        """

        if not llm_action.action:
            return AgentOutput(output="")

        # execute chosen tool / form
        # loop over allowed tools and forms
        chosen_procedure = allowed_procedures.get(llm_action.action, None)
        try:
            if Plugin.is_cat_tool(chosen_procedure):
                # execute tool
                tool_output = await chosen_procedure._arun(llm_action.action_input, stray=stray)
                return AgentOutput(
                    output=tool_output,
                    return_direct=chosen_procedure.return_direct,
                    intermediate_steps=[
                        ((llm_action.action, llm_action.action_input), tool_output)
                    ]
                )
            if Plugin.is_cat_form(chosen_procedure):
                # create form
                form_instance = chosen_procedure(stray)
                # store active form in working memory
                stray.working_memory.active_form = form_instance
                # execute form
                return await self.form_agent.execute(stray)
        except Exception as e:
            log.error(f"Error executing {chosen_procedure.procedure_type} `{chosen_procedure.name}`")
            log.error(e)
            traceback.print_exc()

            return AgentOutput(output="")

    def generate_examples(self, allowed_procedures: Dict[str, CatTool | CatForm]) -> str:
        def get_example(proc):
            example_json = f"""
{{
    "action": "{proc.name}",
    "action_input": "...input here..."
}}"""
            result = f"\nQuestion: {random.choice(proc.start_examples)}"
            result += f"\n```json\n{example_json}\n```"
            result += """
Question: I have no questions
```json
{
    "action": "no_answer",
    "action_input": null
}
```"""
            return result

        list_examples = [get_example(proc) for proc in allowed_procedures.values() if proc.start_examples]

        return "## Here some examples:\n" + "".join(list_examples) if list_examples else ""
