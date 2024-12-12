import inspect
from typing import Callable, List
from pydantic import ConfigDict


# All @tool decorated functions in plugins become a CatTool.
# The difference between base langchain Tool and CatTool is that CatTool has an instance of the cat as attribute
# (set by the plugin manager)
class CatTool:
    def __init__(
        self,
        name: str,
        func: Callable,
        return_direct: bool = False,
        examples: List[str] = None,
    ):
        examples = examples or []

        description = func.__doc__.strip()

        self.func = func
        self.procedure_type = "tool"
        self.name = name
        self.description = description
        self.return_direct = return_direct

        self.triggers_map = {
            "description": [f"{name}: {description}"],
            "start_example": examples,
        }
        # remove cat argument from signature so it does not end up in prompts
        self.signature = f"{inspect.signature(self.func)}".replace(", cat)", ")")

    @property
    def start_examples(self):
        return self.triggers_map["start_example"]

    def __repr__(self) -> str:
        return f"CatTool(name={self.name}, return_direct={self.return_direct}, description={self.description})"

    def run(self, input_by_llm: str, stray) -> str:
        return self.func(input_by_llm, cat=stray)

    model_config = ConfigDict(extra = "allow")


# @tool decorator, a modified version of a langchain Tool that also takes a Cat instance as argument
# adapted from https://github.com/hwchase17/langchain/blob/master/langchain/agents/tools.py
def tool(
    *args: str | Callable, return_direct: bool = False, examples: List[str] = None
) -> Callable:
    """
    Make tools out of functions, can be used with or without arguments.
    Requires:
        - Function must be of type (str, cat) -> str
        - Function must have a docstring
    Examples:
        .. code-block:: python
            @tool
            def search_api(query: str, cat) -> str:
                \"\"\"Searches the API for the query.\"\"\"
                return "https://api.com/search?q=" + query
            @tool("search", return_direct=True)
            def search_api(query: str, cat) -> str:
                \"\"\"Searches the API for the query.\"\"\"
                return "https://api.com/search?q=" + query
    """

    examples = examples or []

    def _make_with_name(tool_name: str) -> Callable:
        def _make_tool(func: Callable[[str], str]) -> CatTool:
            assert func.__doc__, "Function must have a docstring"
            tool_ = CatTool(
                name=tool_name,
                func=func,
                return_direct=return_direct,
                examples=examples,
            )
            return tool_

        return _make_tool

    if len(args) == 1 and isinstance(args[0], str):
        # if the argument is a string, then we use the string as the tool name
        # Example usage: @tool("search", return_direct=True)
        return _make_with_name(args[0])
    if len(args) == 1 and callable(args[0]):
        # if the argument is a function, then we use the function name as the tool name
        # Example usage: @tool
        return _make_with_name(args[0].__name__)(args[0])
    if len(args) == 0:
        # if there are no arguments, then we use the function name as the tool name
        # Example usage: @tool(return_direct=True)
        def _partial(func: Callable[[str], str]) -> CatTool:
            return _make_with_name(func.__name__)(func)

        return _partial

    raise ValueError("Too many arguments for tool decorator")
