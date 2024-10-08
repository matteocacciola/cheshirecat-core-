from cat.looking_glass.cheshire_cat_manager import CheshireCatManager


def job_on_idle_strays(cat_manager: CheshireCatManager) -> None:
    """
    Remove the objects StrayCat, if idle, from the CheshireCat objects contained into the CheshireCatManager.
    """

    ccats = cat_manager.cheshire_cats

    for ccat in ccats:
        for stray in ccat.strays:
            if stray.is_idle:
                ccat.remove_stray(stray)

        if not ccat.has_strays():
            cat_manager.remove_cheshire_cat(ccat)
