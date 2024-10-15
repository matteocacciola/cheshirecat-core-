from typing import Dict
from fastapi import APIRouter, HTTPException, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.memory.models import MemoryCollection

router = APIRouter()


# GET collection list with some metadata
@router.get("/collections")
async def get_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ))
) -> Dict:
    """Get list of available collections"""

    collections_metadata = [{
        "name": str(c),
        "vectors_count": cats.cheshire_cat.memory.vectors.collections[str(c)].get_vectors_count()
    } for c in MemoryCollection]

    return {"collections": collections_metadata}


# DELETE all collections
@router.delete("/collections")
async def wipe_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete and create all collections"""

    ccat = cats.cheshire_cat

    to_return = {str(c): ccat.memory.vectors.collections[str(c)].wipe() for c in MemoryCollection}

    ccat.load_memory()  # recreate the long term memories
    ccat.mad_hatter.find_plugins()

    return {
        "deleted": to_return,
    }


# DELETE one collection
@router.delete("/collections/{collection_id}")
async def wipe_single_collection(
    collection_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete and recreate a collection"""
    # check if collection exists
    if collection_id not in MemoryCollection:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    ccat = cats.cheshire_cat
    ret = ccat.memory.vectors.collections[collection_id].wipe()

    ccat.load_memory()  # recreate the long term memories
    ccat.mad_hatter.find_plugins()

    return {
        "deleted": {collection_id: ret},
    }
