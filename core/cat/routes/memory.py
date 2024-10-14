from typing import Dict, List
from pydantic import BaseModel
from fastapi import Query, APIRouter, HTTPException, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.memory.models import MemoryCollection

router = APIRouter()


class MemoryPointBase(BaseModel):
    content: str
    metadata: Dict = {}


# TODOV2: annotate all endpoints and align internal usage (no qdrant PointStruct, no langchain Document)
class MemoryPoint(MemoryPointBase):
    id: str
    vector: List[float]


# GET memories from recall
@router.get("/recall")
async def recall_memories_from_text(
    text: str = Query(description="Find memories similar to this text."),
    k: int = Query(default=100, description="How many memories to return."),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> Dict:
    def build_memory_dict(metadata, score, vector, id):
        memory_dict = dict(metadata)
        memory_dict.pop("lc_kwargs", None)  # langchain stuff, not needed
        memory_dict["id"] = id
        memory_dict["score"] = float(score)
        memory_dict["vector"] = vector
        return memory_dict

    def get_memories(c: MemoryCollection) -> List:
        # only episodic collection has users
        return ccat.memory.vectors.collections[str(c)].recall_memories_from_embedding(
            query_embedding,
            k=k,
            metadata={"source": cats.stray_cat.user_id} if c == MemoryCollection.EPISODIC else None
        )

    """Search k memories similar to given text."""

    ccat = cats.cheshire_cat

    # Embed the query to plot it in the Memory page
    query_embedding = ccat.embedder.embed_query(text)

    # Loop over collections and retrieve nearby memories
    recalled = {str(c): [
        build_memory_dict(metadata, score, vector, id) for metadata, score, vector, id in get_memories(c)
    ] for c in MemoryCollection}

    return {
        "query": {
            "text": text,
            "vector": query_embedding,
        },
        "vectors": {
            "embedder": str(ccat.embedder.__class__.__name__),  # TODO: should be the config class name
            "collections": recalled,
        },
    }


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


# CREATE a point in memory
@router.post("/collections/{collection_id}/points", response_model=MemoryPoint)
async def create_memory_point(
    collection_id: str,
    point: MemoryPointBase,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.WRITE)),
) -> MemoryPoint:
    """Create a point in memory"""

    # check if collection exists
    if collection_id not in MemoryCollection:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    # do not touch procedural memory
    if collection_id == str(MemoryCollection.PROCEDURAL):
        raise HTTPException(
            status_code=400, detail={"error": "Procedural memory is read-only."}
        )

    ccat = cats.cheshire_cat

    # embed content
    embedding = ccat.embedder.embed_query(point.content)
    
    # ensure source is set
    if not point.metadata.get("source"):
        point.metadata["source"] = cats.stray_cat.user_id # this will do also for declarative memory

    # create point
    qdrant_point = ccat.memory.vectors.collections[collection_id].add_point(
        content=point.content,
        vector=embedding,
        metadata=point.metadata
    )

    return MemoryPoint(
        metadata=qdrant_point.payload["metadata"],
        content=qdrant_point.payload["page_content"],
        vector=qdrant_point.vector,
        id=qdrant_point.id
    )

# DELETE memories
@router.delete("/collections/{collection_id}/points/{point_id}")
async def delete_memory_point(
    collection_id: str,
    point_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete a specific point in memory"""

    # check if collection exists
    if collection_id not in MemoryCollection:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    vector_memory = cats.cheshire_cat.memory.vectors

    # check if point exists
    points = vector_memory.collections[collection_id].retrieve_points([point_id])
    if not points:
        raise HTTPException(status_code=400, detail={"error": "Point does not exist."})

    # delete point
    vector_memory.collections[collection_id].delete_points([point_id])

    return {"deleted": point_id}


@router.delete("/collections/{collection_id}/points")
async def delete_memory_points_by_metadata(
    collection_id: str,
    metadata: Dict = None,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete points in memory by filter"""
    metadata = metadata or {}

    # delete points
    ret = cats.cheshire_cat.memory.vectors.collections[collection_id].delete_points_by_metadata_filter(metadata)

    return {
        "deleted": ret
    }


# DELETE conversation history from working memory
@router.delete("/conversation_history")
async def wipe_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete the specified user's conversation history from working memory"""

    cats.stray_cat.working_memory.history = []

    return {
        "deleted": True,
    }


# GET conversation history from working memory
@router.get("/conversation_history")
async def get_conversation_history(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> Dict:
    """Get the specified user's conversation history from working memory"""

    return {"history": cats.stray_cat.working_memory.history}
