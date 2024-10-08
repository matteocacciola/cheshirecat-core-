from typing import List

from cat.factory.crud_source import CrudSettings
from cat.mad_hatter.decorators import hook


@hook(priority=0)
def factory_allowed_crud_sources(allowed: List[CrudSettings]) -> List:
    """Hook to extend support of crud sources.

    Parameters
    ---------
    allowed : List of CrudSettings classes
        list of allowed crud sources

    Returns
    -------
    supported : List of CrudSettings classes
        list of allowed crud sources
    """
    return allowed
