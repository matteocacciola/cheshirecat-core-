import asyncio


def job_on_idle_strays(lizard: "BillTheLizard", loop) -> bool:
    """
    Remove the objects StrayCat, if idle, from the CheshireCat objects contained into the BillTheLizard.
    """

    ccats = list(lizard.cheshire_cats.values())  # Create a list from the values

    for ccat in ccats:
        for stray in list(ccat.strays):  # Create a copy of strays to iterate over
            if stray.is_idle:
                asyncio.run_coroutine_threadsafe(ccat.remove_stray(stray.user_id), loop=loop).result()

        # Check if the CheshireCat has still strays; if not, remove it
        if not ccat.has_strays():
            asyncio.run_coroutine_threadsafe(lizard.remove_cheshire_cat(ccat.id), loop=loop).result()

    return True