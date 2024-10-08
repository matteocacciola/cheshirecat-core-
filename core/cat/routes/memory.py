from typing import Dict, List
from pydantic import BaseModel
from fastapi import Query, APIRouter, HTTPException, Depends

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource


class MemoryPointBase(BaseModel):
    content: str
    metadata: Dict = {}

# TODOV2: annotate all endpoints and align internal usage (no qdrant PointStruct, no langchain Document)
class MemoryPoint(MemoryPointBase):
    id: str
    vector: List[float]

router = APIRouter()


# GET memories from recall
@router.get("/recall")
async def recall_memories_from_text(
    text: str = Query(description="Find memories similar to this text."),
    k: int = Query(default=100, description="How many memories to return."),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> Dict:
    """Search k memories similar to given text."""

    ccat = cats.cheshire_cat
    vector_memory = ccat.memory.vectors

    # Embed the query to plot it in the Memory page
    query_embedding = ccat.embedder.embed_query(text)
    query = {
        "text": text,
        "vector": query_embedding,
    }

    # Loop over collections and retrieve nearby memories
    collections = list(vector_memory.collections.keys())
    recalled = {}
    for c in collections:
        user_filter = None
        if c == "episodic":
            # only episodic collection has users
            user_filter = {"source": cats.stray_cat.user_id}

        memories = vector_memory.collections[c].recall_memories_from_embedding(
            query_embedding, k=k, metadata=user_filter
        )

        recalled[c] = []
        for metadata, score, vector, id in memories:
            memory_dict = dict(metadata)
            memory_dict.pop("lc_kwargs", None)  # langchain stuff, not needed
            memory_dict["id"] = id
            memory_dict["score"] = float(score)
            memory_dict["vector"] = vector
            recalled[c].append(memory_dict)

    return {
        "query": query,
        "vectors": {
            "embedder": str(
                ccat.embedder.__class__.__name__
            ),  # TODO: should be the config class name
            "collections": recalled,
        },
    }


# GET collection list with some metadata
@router.get("/collections")
async def get_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ))
) -> Dict:
    """Get list of available collections"""

    ccat = cats.cheshire_cat
    vector_memory = ccat.memory.vectors
    collections = list(vector_memory.collections.keys())

    collections_metadata = []

    for c in collections:
        coll_meta = vector_memory.vector_db.get_collection(c)
        collections_metadata += [{"name": c, "vectors_count": coll_meta.vectors_count}]

    return {"collections": collections_metadata}


# DELETE all collections
@router.delete("/collections")
async def wipe_collections(
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete and create all collections"""

    ccat = cats.cheshire_cat
    collections = list(ccat.memory.vectors.collections.keys())
    vector_memory = ccat.memory.vectors

    to_return = {}
    for c in collections:
        ret = vector_memory.vector_db.delete_collection(collection_name=c)
        to_return[c] = ret

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

    ccat = cats.cheshire_cat
    vector_memory = ccat.memory.vectors

    # check if collection exists
    collections = list(vector_memory.collections.keys())
    if collection_id not in collections:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    to_return = {}

    ret = vector_memory.vector_db.delete_collection(collection_name=collection_id)
    to_return[collection_id] = ret

    ccat.load_memory()  # recreate the long term memories
    ccat.mad_hatter.find_plugins()

    return {
        "deleted": to_return,
    }


# CREATE a point in memory
@router.post("/collections/{collection_id}/points", response_model=MemoryPoint)
async def create_memory_point(
    collection_id: str,
    point: MemoryPointBase,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.WRITE)),
) -> MemoryPoint:
    """Create a point in memory"""

    # do not touch procedural memory
    if collection_id == "procedural":
        raise HTTPException(
            status_code=400, detail={"error": "Procedural memory is read-only."}
        )

    stray = cats.stray_cat
    ccat = cats.cheshire_cat
    memory_collections = ccat.memory.vectors.collections

    # check if collection exists
    collections = list(memory_collections.keys())
    if collection_id not in collections:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )
    
    # embed content
    embedding = ccat.embedder.embed_query(point.content)
    
    # ensure source is set
    if not point.metadata.get("source"):
        point.metadata["source"] = stray.user_id # this will do also for declarative memory

    # create point
    qdrant_point = memory_collections[collection_id].add_point(
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

    ccat = cats.cheshire_cat
    vector_memory = ccat.memory.vectors

    # check if collection exists
    collections = list(vector_memory.collections.keys())
    if collection_id not in collections:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    # check if point exists
    points = vector_memory.vector_db.retrieve(
        collection_name=collection_id,
        ids=[point_id],
    )
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

    ccat = cats.cheshire_cat
    vector_memory = ccat.memory.vectors

    # delete points
    vector_memory.collections[collection_id].delete_points_by_metadata_filter(metadata)

    return {
        "deleted": []  # TODO: Qdrant does not return deleted points?
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
