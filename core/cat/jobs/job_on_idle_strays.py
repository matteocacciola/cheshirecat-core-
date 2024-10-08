from cat.looking_glass.cheshire_cat_manager import CheshireCatManager


def job_on_idle_strays(cat_manager: CheshireCatManager) -> None:
    """
    Remove the objects StrayCat if idle.
    """
    for _, stray in cat_manager.strays.items():
        if stray.is_idle:
            cat_manager.remove_stray(stray.user_id)
