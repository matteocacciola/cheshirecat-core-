from typing import Dict, List, Any
from pydantic import BaseModel
from fastapi import Query, APIRouter, HTTPException, Depends
import time
from qdrant_client.http.models import UpdateResult, Record

from cat.auth.connection import HTTPAuth, ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource
from cat.factory.embedder import get_embedder_config_class_from_model
from cat.memory.vector_memory_collection import VectoryMemoryCollectionTypes

router = APIRouter()


class MemoryPointBase(BaseModel):
    content: str
    metadata: Dict = {}


# TODOV2: annotate all endpoints and align internal usage (no qdrant PointStruct, no langchain Document)
class MemoryPoint(MemoryPointBase):
    id: str
    vector: List[float]


class RecallResponseQuery(BaseModel):
    text: str
    vector: List[float]


class RecallResponseVectors(BaseModel):
    embedder: str
    collections: Dict[str, List[Dict[str, Any]]]


class RecallResponse(BaseModel):
    query: RecallResponseQuery
    vectors: RecallResponseVectors


class GetPointsInCollectionResponse(BaseModel):
    points: List[Record]
    next_offset: int | str | None


# GET memories from recall
@router.get("/recall", response_model=RecallResponse)
async def recall_memory_points_from_text(
    text: str = Query(description="Find memories similar to this text."),
    k: int = Query(default=100, description="How many memories to return."),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.READ)),
) -> RecallResponse:
    """Search k memories similar to given text."""

    def build_memory_dict(metadata, score, vector, id):
        memory_dict = dict(metadata)
        memory_dict.pop("lc_kwargs", None)  # langchain stuff, not needed
        memory_dict["id"] = id
        memory_dict["score"] = float(score)
        memory_dict["vector"] = vector
        return memory_dict

    def get_memories(c: VectoryMemoryCollectionTypes) -> List:
        # only episodic collection has users
        return ccat.memory.vectors.collections[str(c)].recall_memories_from_embedding(
            query_embedding,
            k=k,
            metadata={"source": cats.stray_cat.user_id} if c == VectoryMemoryCollectionTypes.EPISODIC else None
        )

    ccat = cats.cheshire_cat

    # Embed the query to plot it in the Memory page
    query_embedding = ccat.embedder.embed_query(text)

    # Loop over collections and retrieve nearby memories
    recalled = {str(c): [
        build_memory_dict(metadata, score, vector, id) for metadata, score, vector, id in get_memories(c)
    ] for c in VectoryMemoryCollectionTypes}

    return RecallResponse(
        query=RecallResponseQuery(text=text, vector=query_embedding),
        vectors=RecallResponseVectors(
            embedder=get_embedder_config_class_from_model(ccat.embedder.__class__, ccat.mad_hatter),
            collections=recalled
        )
    )


# CREATE a point in memory
@router.post("/collections/{collection_id}/points", response_model=MemoryPoint)
async def create_memory_point(
    collection_id: str,
    point: MemoryPointBase,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.WRITE)),
) -> MemoryPoint:
    """Create a point in memory"""

    # check if collection exists
    if collection_id not in VectoryMemoryCollectionTypes:
        raise HTTPException(
            status_code=400, detail={"error": "Collection does not exist."}
        )

    # do not touch procedural memory
    if collection_id == str(VectoryMemoryCollectionTypes.PROCEDURAL):
        raise HTTPException(
            status_code=400, detail={"error": "Procedural memory is read-only."}
        )

    ccat = cats.cheshire_cat

    # embed content
    embedding = ccat.embedder.embed_query(point.content)

    # ensure source is set
    if not point.metadata.get("source"):
        point.metadata["source"] = cats.stray_cat.user_id  # this will do also for declarative memory

    # ensure when is set
    if not point.metadata.get("when"):
        point.metadata["when"] = time.time() #if when is not in the metadata set the current time

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
@router.delete("/collections/{collection_id}/points/{point_id}", response_model=Dict[str, str])
async def delete_memory_point(
    collection_id: str,
    point_id: str,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete a specific point in memory"""

    # check if collection exists
    if collection_id not in VectoryMemoryCollectionTypes:
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


@router.delete("/collections/{collection_id}/points", response_model=Dict[str, UpdateResult])
async def delete_memory_points_by_metadata(
    collection_id: str,
    metadata: Dict = None,
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> Dict:
    """Delete points in memory by filter"""
    metadata = metadata or {}

    # delete points
    ret = cats.cheshire_cat.memory.vectors.collections[collection_id].delete_points_by_metadata_filter(metadata)

    return {"deleted": ret}


# GET all the points from a single collection
@router.get("/collections/{collection_id}/points", response_model=GetPointsInCollectionResponse)
async def get_points_in_collection(
    collection_id: str,
    limit: int = Query(
        default=100,
        description="How many points to return"
    ),
    offset: str = Query(
        default=None,
        description="If provided (or not empty string) - skip points with ids less than given `offset`"
    ),
    cats: ContextualCats = Depends(HTTPAuth(AuthResource.MEMORY, AuthPermission.DELETE)),
) -> GetPointsInCollectionResponse:
    """Retrieve all the points from a single collection

    Example
    ----------
    ```
    collection = "declarative"
    res = requests.get(
        f"http://localhost:1865/memory/collections/{collection}/points",
    )
    json = res.json()
    points = json["points"]

    for point in points:
        payload = point["payload"]
        vector = point["vector"]
        print(payload)
        print(vector)
    ```

    Example using offset
    ----------
    ```
    # get all the points with limit 10
    limit = 10
    next_offset = ""
    collection = "declarative"

    while True:
        res = requests.get(
            f"http://localhost:1865/memory/collections/{collection}/points?limit={limit}&offset={next_offset}",
        )
        json = res.json()
        points = json["points"]
        next_offset = json["next_offset"]

        for point in points:
            payload = point["payload"]
            vector = point["vector"]
            print(payload)
            print(vector)

        if next_offset is None:
            break
    ```
    """

    # do not allow procedural memory reads via network
    if collection_id == "procedural":
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Procedural memory is not readable via API"
            }
        )

    # check if collection exists
    if collection_id not in VectoryMemoryCollectionTypes:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Collection does not exist."
            }
        )

    # if offset is empty string set to null
    if offset == "":
        offset = None

    memory_collection = cats.stray_cat.memory.vectors.collections[collection_id]
    points, next_offset = memory_collection.get_all_points(limit=limit, offset=offset)

    return GetPointsInCollectionResponse(points=points, next_offset=next_offset)
