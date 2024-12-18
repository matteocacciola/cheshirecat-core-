from typing import Dict

from cat.mad_hatter.decorators import hook


@hook(priority=10)
def fast_reply(f_reply: Dict, cat) -> Dict | None:
    user_msg = "hello"
    fast_reply_msg = "This is a fast reply"

    if user_msg in cat.working_memory.user_message.text:
        f_reply["output"] = fast_reply_msg

    return f_reply