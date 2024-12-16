import asyncio

from cat.looking_glass.bill_the_lizard import BillTheLizard


def job_on_idle_strays() -> bool:
    """
    Remove the objects StrayCat, if idle, from the CheshireCat objects contained into the BillTheLizard.
    """

    lizard = BillTheLizard()  # Get the BillTheLizard

    cats = list(lizard.cheshire_cats.values())  # Create a list from the values

    for cat in cats:
        for stray in list(cat.strays):  # Create a copy of strays to iterate over
            if stray.is_idle:
                asyncio.run(cat.remove_stray(stray.user.id))

        # Check if the CheshireCat has still strays; if not, remove it
        if not cat.has_strays():
            asyncio.run(lizard.remove_cheshire_cat(cat.id))

    return True