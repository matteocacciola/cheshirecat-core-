from typing import Dict, List
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.exceptions import CustomNotFoundException
from cat.memory.vector_memory_collection import VectoryMemoryCollectionTypes

router = APIRouter()


class GetCollectionsItem(BaseModel):
    name: str
    vectors_count: int


class GetCollectionsResponse(BaseModel):
    collections: List[GetCollectionsItem]


class WipeCollectionsResponse(BaseModel):
    deleted: Dict[str, bool]


# GET collection list with some metadata
@router.get("/collections", response_model=GetCollectionsResponse)
async def get_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ))
) -> GetCollectionsResponse:
    """Get list of available collections"""

    collections_metadata = [GetCollectionsItem(
        name=str(c),
        vectors_count=cats.cheshire_cat.memory.vectors.collections[str(c)].get_vectors_count()
    ) for c in VectoryMemoryCollectionTypes]

    return GetCollectionsResponse(collections=collections_metadata)


# DELETE all collections
@router.delete("/collections", response_model=WipeCollectionsResponse)
async def destroy_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> WipeCollectionsResponse:
    """Delete and create all collections"""

    ccat = cats.cheshire_cat

    to_return = {str(c): ccat.memory.vectors.collections[str(c)].destroy_collection() for c in VectoryMemoryCollectionTypes}

    ccat.load_memory()  # recreate the long term memories
    ccat.plugin_manager.find_plugins()

    return WipeCollectionsResponse(deleted=to_return)


# DELETE one collection
@router.delete("/collections/{collection_id}", response_model=WipeCollectionsResponse)
async def destroy_single_collection(
    collection_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> WipeCollectionsResponse:
    """Delete and recreate a collection"""

    # check if collection exists
    if collection_id not in VectoryMemoryCollectionTypes:
        raise CustomNotFoundException("Collection does not exist.")

    ccat = cats.cheshire_cat
    ret = ccat.memory.vectors.collections[collection_id].destroy_collection()

    ccat.load_memory()  # recreate the long term memories
    ccat.plugin_manager.find_plugins()

    return WipeCollectionsResponse(deleted={collection_id: ret})
