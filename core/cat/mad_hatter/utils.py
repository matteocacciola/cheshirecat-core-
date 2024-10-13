from copy import deepcopy
import traceback

from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter


# execute requested hook
def execute_hook(mad_hatter: MadHatter, hook_name, *args, cat):
    # check if hook is supported
    if hook_name not in mad_hatter.hooks.keys():
        raise Exception(f"Hook {hook_name} not present in any plugin")

    # Hook has no arguments (aside cat)
    #  no need to pipe
    if len(args) == 0:
        for hook in mad_hatter.hooks[hook_name]:
            try:
                log.debug(
                    f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
                )
                hook.function(cat=cat)
            except Exception as e:
                log.error(f"Error in plugin {hook.plugin_id}::{hook.name}")
                log.error(e)
                plugin_obj = mad_hatter.plugins[hook.plugin_id]
                log.warning(plugin_obj.plugin_specific_error_message())
                traceback.print_exc()
        return

    # Hook with arguments.
    #  First argument is passed to `execute_hook` is the pipeable one.
    #  We call it `tea_cup` as every hook called will receive it as an input,
    #  can add sugar, milk, or whatever, and return it for the next hook
    tea_cup = deepcopy(args[0])

    # run hooks
    for hook in mad_hatter.hooks[hook_name]:
        try:
            # pass tea_cup to the hooks, along other args
            # hook has at least one argument, and it will be piped
            log.debug(
                f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
            )
            tea_spoon = hook.function(
                deepcopy(tea_cup), *deepcopy(args[1:]), cat=cat
            )
            # log.debug(f"Hook {hook.plugin_id}::{hook.name} returned {tea_spoon}")
            if tea_spoon is not None:
                tea_cup = tea_spoon
        except Exception as e:
            log.error(f"Error in plugin {hook.plugin_id}::{hook.name}")
            log.error(e)
            plugin_obj = mad_hatter.plugins[hook.plugin_id]
            log.warning(plugin_obj.plugin_specific_error_message())
            traceback.print_exc()

    # tea_cup has passed through all hooks. Return final output
    return tea_cup